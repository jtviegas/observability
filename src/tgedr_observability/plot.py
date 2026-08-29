"""Helpers to read exported OpenTelemetry metrics files and plot them.

The file exporter configured by `Metrics` writes `ConsoleMetricExporter`
output: one JSON document per flush, appended to the file. A single file can
therefore contain several concatenated JSON documents. These helpers parse that
format and render a metric as a time series: one line per tag (attribute) value,
with the export timestamp on the x-axis.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib as mpl

mpl.use("Agg")  # non-interactive backend, safe for headless/CI usage
import matplotlib.pyplot as plt

from tgedr_observability.commons import ObservabilityError

if TYPE_CHECKING:
    from collections.abc import Iterator


def _iter_json_documents(text: str) -> Iterator[dict]:
    """Yield successive JSON documents from concatenated exporter output."""
    decoder = json.JSONDecoder()
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index].isspace():
            index += 1
        if index >= length:
            break
        document, offset = decoder.raw_decode(text, index)
        yield document
        index = offset


def load_metric_series(
    path: str | Path,
    metric_name: str | None = None,
    attr_key: str | None = None,
) -> tuple[str, str, dict[str, list[tuple[datetime, float]]]]:
    """Extract time series per tag value for one metric from a metrics file.

    Args:
        path: path to the metrics export file (one or more JSON documents).
        metric_name: metric to read; defaults to the first metric found.
        attr_key: attribute used to split series; defaults to the first
            attribute key found on a data point.

    Returns:
        A tuple of (metric_name, attr_key, series) where `series` maps each tag
        value to a list of `(timestamp, value)` pairs sorted by timestamp.

    Raises:
        ObservabilityError: when no matching metric is found.
    """
    text = Path(path).read_text(encoding="utf-8")

    resolved_name: str | None = None
    resolved_attr = attr_key
    series: dict[str, list[tuple[datetime, float]]] = {}

    for document in _iter_json_documents(text):
        for resource_metric in document.get("resource_metrics", []):
            for scope_metric in resource_metric.get("scope_metrics", []):
                for metric in scope_metric.get("metrics", []):
                    if metric_name is not None and metric["name"] != metric_name:
                        continue
                    resolved_name = metric["name"]
                    for point in metric.get("data", {}).get("data_points", []):
                        attributes = point.get("attributes", {}) or {}
                        if resolved_attr is None:
                            resolved_attr = next(iter(attributes), "index")
                        label = str(attributes.get(resolved_attr, "?"))
                        timestamp = datetime.fromtimestamp(point["time_unix_nano"] / 1_000_000_000, tz=UTC)
                        series.setdefault(label, []).append((timestamp, float(point["value"])))

    if resolved_name is None:
        error_message = f"no matching metric found in {path}"
        raise ObservabilityError(error_message)

    for points in series.values():
        points.sort(key=lambda item: item[0])

    return resolved_name, resolved_attr or "index", series


def plot_metric(
    path: str | Path,
    metric_name: str | None = None,
    attr_key: str | None = None,
    save_path: str | Path | None = None,
) -> str | None:
    """Read a metrics export file and plot a metric as a time series.

    Draws one line per tag (attribute) value, with the export timestamp on the
    x-axis.

    Args:
        path: path to the metrics export file.
        metric_name: metric to plot; defaults to the first metric found.
        attr_key: attribute used to split series; defaults to the first found.
        save_path: when set, the figure is written here and the path returned;
            otherwise the figure is shown interactively and `None` is returned.

    Returns:
        The saved file path (as a string) when `save_path` is provided, else
        `None`.

    Example:
        uv run python -c "from tgedr_observability.plot import plot_metric; plot_metric('../fda_faers/otel/metrics','new_rows', 'table', save_path='output.png')"
    """
    resolved_name, resolved_attr, series = load_metric_series(path, metric_name, attr_key)

    fig, ax = plt.subplots(figsize=(9, 5))
    for label in sorted(series):
        points = series[label]
        timestamps = [ts for ts, _ in points]
        values = [value for _, value in points]
        ax.plot(timestamps, values, marker="o", linewidth=2, label=label)

    ax.set_title(f"{resolved_name} over time")
    ax.set_xlabel("timestamp")
    ax.set_ylabel(resolved_name)
    ax.legend(title=resolved_attr)
    ax.grid(visible=True, linestyle="--", alpha=0.4)
    fig.autofmt_xdate()
    fig.tight_layout()

    if save_path is not None:
        fig.savefig(save_path, dpi=120)
        plt.close(fig)
        return str(save_path)

    plt.show()
    plt.close(fig)
    return None
