"""Unit tests for the metrics plotting helpers."""

from datetime import datetime
from pathlib import Path

import pytest

from tgedr_observability.commons import ObservabilityError
from tgedr_observability.plot import load_metric_series, plot_metric


SAMPLE = str(Path(__file__).parent.parent / "resources" / "metrics_sample.json")


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


def test_load_metric_series_missing_metric_raises() -> None:
    with pytest.raises(ObservabilityError, match="no matching metric"):
        load_metric_series(SAMPLE, metric_name="does_not_exist")


def test_plot_metric_saves_file(tmp_path: Path) -> None:
    out = tmp_path / "plot.png"

    result = plot_metric(SAMPLE, save_path=out)

    assert result == str(out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_plot_metric_show(monkeypatch) -> None:
    calls = {"show": 0}
    monkeypatch.setattr("tgedr_observability.plot.plt.show", lambda: calls.__setitem__("show", calls["show"] + 1))

    result = plot_metric(SAMPLE)

    assert result is None
    assert calls["show"] == 1
