"""Helpers to read exported OpenTelemetry metrics files and plot them.

The file exporter configured by `Metrics` writes `ConsoleMetricExporter`
output: one JSON document per flush, appended to the file. A single file can
therefore contain several concatenated JSON documents. These helpers parse that
format and render a gauge metric as a line graph across its tag (attribute)
values.
"""

from __future__ import annotations

import json
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


def load_metric_points(
    path: str | Path,
    metric_name: str | None = None,
    attr_key: str | None = None,
) -> tuple[str, str, list[tuple[str, float]]]:
    """Extract (label, value) pairs for one metric from an exported metrics file.

    Args:
        path: path to the metrics export file (one or more JSON documents).
        metric_name: metric to read; defaults to the first metric found.
        attr_key: attribute used as the x-axis label; defaults to the first
            attribute key found on a data point.

    Returns:
        A tuple of (metric_name, attr_key, [(label, value), ...]) taking the
        last exported value for each label.

    Raises:
        ObservabilityError: when no matching metric is found.
    """
    text = Path(path).read_text(encoding="utf-8")

    resolved_name: str | None = None
    resolved_attr = attr_key
    values_by_label: dict[str, float] = {}

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
                        values_by_label[label] = float(point["value"])

    if resolved_name is None:
        error_message = f"no matching metric found in {path}"
        raise ObservabilityError(error_message)

    return resolved_name, resolved_attr or "index", list(values_by_label.items())


def plot_metric(
    path: str | Path,
    metric_name: str | None = None,
    attr_key: str | None = None,
    save_path: str | Path | None = None,
) -> str | None:
    """Read a metrics export file and plot a metric as a line graph.

    Points are sorted by value (descending) so the connecting line is readable
    for categorical x-axis (tag) values.

    Args:
        path: path to the metrics export file.
        metric_name: metric to plot; defaults to the first metric found.
        attr_key: attribute used as the x-axis; defaults to the first found.
        save_path: when set, the figure is written here and the path returned;
            otherwise the figure is shown interactively and `None` is returned.

    Returns:
        The saved file path (as a string) when `save_path` is provided, else
        `None`.
    """
    resolved_name, resolved_attr, points = load_metric_points(path, metric_name, attr_key)
    points.sort(key=lambda item: item[1], reverse=True)
    labels = [label for label, _ in points]
    values = [value for _, value in points]

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(labels, values, marker="o", linewidth=2)
    for x, y in zip(labels, values, strict=True):
        ax.annotate(f"{y:,.0f}", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8)
    ax.set_title(f"{resolved_name} by {resolved_attr}")
    ax.set_xlabel(resolved_attr)
    ax.set_ylabel(resolved_name)
    ax.grid(visible=True, linestyle="--", alpha=0.4)
    fig.tight_layout()

    if save_path is not None:
        fig.savefig(save_path, dpi=120)
        plt.close(fig)
        return str(save_path)

    plt.show()
    plt.close(fig)
    return None
