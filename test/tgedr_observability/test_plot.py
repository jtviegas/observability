"""Unit tests for the metrics plotting helpers."""

from datetime import datetime
from pathlib import Path

import pytest

from tgedr_observability.commons import ObservabilityError
from tgedr_observability.plot import load_metric_series, plot_metric


SAMPLE = str(Path(__file__).parent.parent / "resources" / "metrics_sample.json")
PERIOD_SAMPLE = str(Path(__file__).parent.parent / "resources" / "metrics_period_sample.json")


def _write_xattr_doc(tmp_path: Path) -> Path:
    """Doc with an extra numeric 'day' tag to use as the x-axis."""
    from json import dumps

    def point(table: str, day: int, value: int) -> dict:
        return {"attributes": {"table": table, "day": day}, "time_unix_nano": 1787862, "value": value}

    doc = {
        "resource_metrics": [
            {
                "resource": {"attributes": {}},
                "scope_metrics": [
                    {
                        "scope": {"name": "fda_faers.ingest_period_files"},
                        "metrics": [
                            {
                                "name": "new_rows",
                                "description": "",
                                "unit": "1",
                                "data": {
                                    "data_points": [
                                        point("drug", 1, 872470),
                                        point("reac", 1, 980673),
                                        point("drug", 2, 999),
                                        point("reac", 2, 123),
                                    ]
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }
    target = tmp_path / "xattr.json"
    target.write_text(dumps(doc), encoding="utf-8")
    return target



def _write_multi_doc(tmp_path: Path) -> Path:
    """Two exporter documents at different timestamps for the same tags."""
    doc = Path(__file__).parent.parent / "resources" / "metrics_sample.json"
    text = doc.read_text(encoding="utf-8")
    later = (
        '{"resource_metrics":[{"resource":{"attributes":{}},"scope_metrics":'
        '[{"scope":{"name":"fda_faers.ingest_period_files"},"metrics":'
        '[{"name":"new_rows","description":"","unit":"1","data":{"data_points":'
        '[{"attributes":{"table":"demo"},"time_unix_nano":1787862339983853728,"value":999},'
        '{"attributes":{"table":"drug"},"time_unix_nano":1787862339983853728,"value":123}]}}]}]}]}'
    )
    target = tmp_path / "multi.json"
    target.write_text(text + "\n" + later, encoding="utf-8")
    return target


def test_load_metric_series_defaults() -> None:
    name, attr, series = load_metric_series(SAMPLE)

    assert name == "new_rows"
    assert attr == "table"
    assert set(series) == {"drug", "reac", "demo"}
    # one point per tag in the single-timestamp sample
    assert series["drug"][0][1] == 872470.0
    assert isinstance(series["drug"][0][0], datetime)


def test_load_metric_series_explicit_metric_and_attr() -> None:
    name, attr, series = load_metric_series(SAMPLE, metric_name="new_rows", attr_key="table")

    assert name == "new_rows"
    assert attr == "table"
    assert len(series) == 3


def test_load_metric_series_multi_document_builds_timeline(tmp_path: Path) -> None:
    target = _write_multi_doc(tmp_path)

    _, _, series = load_metric_series(target)

    # 'demo' now has two points across two timestamps, sorted ascending.
    assert len(series["demo"]) == 2
    assert series["demo"][0][0] < series["demo"][1][0]
    assert series["demo"][1][1] == 999.0


def test_load_metric_series_latest_only_keeps_newest_point_per_tag(tmp_path: Path) -> None:
    """latest_only collapses each tag to its most recently exported point."""
    target = _write_multi_doc(tmp_path)

    _, _, series = load_metric_series(target, latest_only=True)

    assert len(series["demo"]) == 1
    assert series["demo"][0][1] == 999.0


def test_load_metric_series_latest_only_default_keeps_whole_timeline(tmp_path: Path) -> None:
    """Without latest_only the full timeline is preserved."""
    target = _write_multi_doc(tmp_path)

    _, _, series = load_metric_series(target)

    assert len(series["demo"]) == 2


def test_load_metric_series_latest_only_with_x_attr_key(tmp_path: Path) -> None:
    """latest_only filters on the export timestamp even when x-axis is a tag."""
    from json import dumps

    doc = {
        "resource_metrics": [
            {
                "resource": {"attributes": {}},
                "scope_metrics": [
                    {
                        "scope": {"name": "s"},
                        "metrics": [
                            {
                                "name": "m",
                                "description": "",
                                "unit": "1",
                                "data": {
                                    "data_points": [
                                        {"attributes": {"table": "drug", "day": 1}, "time_unix_nano": 1000, "value": 100},
                                        {"attributes": {"table": "drug", "day": 2}, "time_unix_nano": 2000, "value": 200},
                                        {"attributes": {"table": "drug", "day": 3}, "time_unix_nano": 3000, "value": 300},
                                    ]
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }
    target = tmp_path / "xattr_latest.json"
    target.write_text(dumps(doc), encoding="utf-8")

    _, _, series = load_metric_series(target, attr_key="table", x_attr_key="day", latest_only=True)

    # The newest export (timestamp 3000) carries day=3, so only that point remains,
    # keyed by the (table, day) combination.
    assert series["drug|3"] == [(3.0, 300.0)]


def test_load_metric_series_latest_only_uses_combined_attr_x_identity(tmp_path: Path) -> None:
    """latest_only resolves per (attr_key, x_attr_key) combination, not per attr_key alone."""
    from json import dumps

    def point(table: str, day: int, ts: int, value: int) -> dict:
        return {"attributes": {"table": table, "day": day}, "time_unix_nano": ts, "value": value}

    doc = {
        "resource_metrics": [
            {
                "resource": {"attributes": {}},
                "scope_metrics": [
                    {
                        "scope": {"name": "s"},
                        "metrics": [
                            {
                                "name": "m",
                                "description": "",
                                "unit": "1",
                                "data": {
                                    "data_points": [
                                        point("drug", 1, 1000, 10),
                                        point("drug", 1, 3000, 30),
                                        point("drug", 2, 2000, 20),
                                        point("reac", 1, 1500, 40),
                                    ]
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }
    target = tmp_path / "combined.json"
    target.write_text(dumps(doc), encoding="utf-8")

    # x-axis = 'day', one label per (table, day) combination.
    _, _, series = load_metric_series(target, attr_key="table", x_attr_key="day", latest_only=True)

    # drug|1 picks its latest point (ts 3000 -> day 1, value 30); drug|2 keeps ts 2000.
    assert series["drug|1"] == [(1.0, 30.0)]
    assert series["drug|2"] == [(2.0, 20.0)]
    assert series["reac|1"] == [(1.0, 40.0)]


def test_load_metric_series_missing_metric_raises() -> None:
    with pytest.raises(ObservabilityError, match="no matching metric"):
        load_metric_series(SAMPLE, metric_name="does_not_exist")


def test_load_metric_series_x_attr_key(tmp_path: Path) -> None:
    """x_attr_key makes the x-axis a tag value instead of the timestamp."""
    target = _write_xattr_doc(tmp_path)

    name, attr, series = load_metric_series(target, attr_key="table", x_attr_key="day")

    assert name == "new_rows"
    assert attr == "table"
    # one label per (table, day) combination.
    assert set(series) == {"drug|1", "drug|2", "reac|1", "reac|2"}
    # x-axis is the numeric 'day' tag, not a datetime.
    assert series["drug|1"] == [(1.0, 872470.0)]
    assert series["drug|2"] == [(2.0, 999.0)]


def test_load_metric_series_x_attr_key_string(tmp_path: Path) -> None:
    """String tag values are preserved on the x-axis."""
    doc = (
        '{"resource_metrics":[{"resource":{"attributes":{}},"scope_metrics":'
        '[{"scope":{"name":"s"},"metrics":[{"name":"m","description":"","unit":"1",'
        '"data":{"data_points":['
        '{"attributes":{"group":"a","key":"x"},"time_unix_nano":1,"value":1},'
        '{"attributes":{"group":"b","key":"x"},"time_unix_nano":1,"value":2}'
        ']}}]}]}]}'
    )
    target = tmp_path / "s.json"
    target.write_text(doc, encoding="utf-8")

    _, _, series = load_metric_series(target, attr_key="key", x_attr_key="group")

    # label is the (key, group) combination: both points share key='x'.
    assert series["x|a"] == [("a", 1.0)]
    assert series["x|b"] == [("b", 2.0)]


def test_load_metric_series_x_attr_key_bool(tmp_path: Path) -> None:
    """Boolean tag values are stringified on the x-axis."""
    from json import dumps

    doc = {
        "resource_metrics": [
            {
                "resource": {"attributes": {}},
                "scope_metrics": [
                    {
                        "scope": {"name": "s"},
                        "metrics": [
                            {
                                "name": "m",
                                "description": "",
                                "unit": "1",
                                "data": {
                                    "data_points": [
                                        {"attributes": {"group": "a", "ready": True}, "time_unix_nano": 1, "value": 1},
                                        {"attributes": {"group": "a", "ready": False}, "time_unix_nano": 1, "value": 2},
                                    ]
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }
    target = tmp_path / "b.json"
    target.write_text(dumps(doc), encoding="utf-8")

    _, _, series = load_metric_series(target, attr_key="group", x_attr_key="ready")

    # label is the (group, ready) combination.
    assert series["a|False"] == [("False", 2.0)]
    assert series["a|True"] == [("True", 1.0)]



def test_plot_metric_x_attr_key_saves_file(tmp_path: Path) -> None:
    """plot_metric draws against a tag value on the x-axis."""
    target = _write_xattr_doc(tmp_path)
    out = tmp_path / "plot_x.png"

    result = plot_metric(target, attr_key="table", x_attr_key="day", save_path=out)

    assert result == str(out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_load_metric_series_period_sample() -> None:
    """period tag drives the x-axis, one line per (table, period) combination."""
    name, attr, series = load_metric_series(PERIOD_SAMPLE, attr_key="table", x_attr_key="period")

    assert name == "new_rows"
    assert attr == "table"
    assert set(series) == {"drug|1", "drug|2", "drug|3", "reac|1", "reac|2", "reac|3", "demo|1", "demo|2", "demo|3"}
    assert series["drug|1"] == [(1.0, 872470.0)]
    assert series["drug|2"] == [(2.0, 900001.0)]
    assert series["drug|3"] == [(3.0, 930004.0)]
    assert series["reac|1"] == [(1.0, 980673.0)]
    assert series["demo|1"] == [(1.0, 234146.0)]


def test_plot_metric_period_sample_creates_image(tmp_path: Path) -> None:
    """Plot the period sample to a graph image using x_attr_key."""
    out = tmp_path / "new_rows_by_period.png"

    result = plot_metric(PERIOD_SAMPLE, attr_key="table", x_attr_key="period", save_path=out)

    assert result == str(out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_plot_metric_latest_only_saves_file(tmp_path: Path) -> None:
    """plot_metric forwards latest_only and still renders a file."""
    doc = (
        '{"resource_metrics":[{"resource":{"attributes":{}},"scope_metrics":'
        '[{"scope":{"name":"s"},"metrics":[{"name":"m","description":"","unit":"1",'
        '"data":{"data_points":['
        '{"attributes":{"table":"a"},"time_unix_nano":1000,"value":10},'
        '{"attributes":{"table":"a"},"time_unix_nano":2000,"value":20}'
        ']}}]}]}]}'
    )
    target = tmp_path / "latest.json"
    target.write_text(doc, encoding="utf-8")
    out = tmp_path / "latest.png"

    result = plot_metric(target, attr_key="table", latest_only=True, save_path=out)

    assert result == str(out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_plot_metric_saves_file(tmp_path: Path) -> None:
    out = tmp_path / "plot.png"

    result = plot_metric(SAMPLE, save_path=out)

    assert result == str(out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_plot_metric_positional_save_path_backward_compatible(tmp_path: Path) -> None:
    """Save_path passed positionally (4th arg) still saves a file."""
    out = tmp_path / "plot_positional.png"

    result = plot_metric(SAMPLE, "new_rows", "table", out)

    assert result == str(out)
    assert out.exists()
    assert out.stat().st_size > 0



def test_plot_metric_show(monkeypatch) -> None:
    calls = {"show": 0}
    monkeypatch.setattr("tgedr_observability.plot.plt.show", lambda: calls.__setitem__("show", calls["show"] + 1))

    result = plot_metric(SAMPLE)

    assert result is None
    assert calls["show"] == 1
