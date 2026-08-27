"""Unit tests for the metrics plotting helpers."""

from pathlib import Path

import pytest

from tgedr_observability.commons import ObservabilityError
from tgedr_observability.plot import load_metric_points, plot_metric


SAMPLE = str(Path(__file__).parent.parent / "resources" / "metrics_sample.json")


def _write_multi_doc(tmp_path: Path) -> Path:
    """Two concatenated exporter documents; the second overrides 'demo'."""
    doc = Path(__file__).parent.parent / "resources" / "metrics_sample.json"
    text = doc.read_text(encoding="utf-8")
    override = (
        '{"resource_metrics":[{"resource":{"attributes":{}},"scope_metrics":'
        '[{"scope":{"name":"fda_faers.ingest_period_files"},"metrics":'
        '[{"name":"new_rows","description":"","unit":"1","data":{"data_points":'
        '[{"attributes":{"table":"demo"},"value":999}]}}]}]}]}'
    )
    target = tmp_path / "multi.json"
    target.write_text(text + "\n" + override, encoding="utf-8")
    return target


def test_load_metric_points_defaults() -> None:
    name, attr, points = load_metric_points(SAMPLE)

    assert name == "new_rows"
    assert attr == "table"
    assert dict(points) == {"drug": 872470.0, "reac": 980673.0, "demo": 234146.0}


def test_load_metric_points_explicit_metric_and_attr() -> None:
    name, attr, points = load_metric_points(SAMPLE, metric_name="new_rows", attr_key="table")

    assert name == "new_rows"
    assert attr == "table"
    assert len(points) == 3


def test_load_metric_points_multi_document_takes_last_value(tmp_path: Path) -> None:
    target = _write_multi_doc(tmp_path)

    _, _, points = load_metric_points(target)

    # 'demo' is overridden by the second document.
    assert dict(points)["demo"] == 999.0


def test_load_metric_points_missing_metric_raises() -> None:
    with pytest.raises(ObservabilityError, match="no matching metric"):
        load_metric_points(SAMPLE, metric_name="does_not_exist")


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
