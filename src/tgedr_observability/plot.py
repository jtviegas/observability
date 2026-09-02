"""Helpers to read exported OpenTelemetry metrics files and plot them.

The file exporter configured by `Metrics` writes `ConsoleMetricExporter`
output: one JSON document per flush, appended to the file. A single file can
therefore contain several concatenated JSON documents. These helpers parse that
format and render a metric as a series of lines (one per tag/attribute value).

By default the x-axis is the export timestamp, producing a time series. When an
`x_attr_key` tag is supplied, the x-axis is instead taken from the value of that
tag, while each line still represents the value of another tag (`attr_key`) for
its own value. This lets you plot e.g. a per-key metric against another numeric
attribute rather than time.

When a metric carries more than one tag, the series identity is the
combination of `attr_key` and `x_attr_key` values (labels join the values with
'|'), so `latest_only` resolves the newest point per tag combination instead of
per single tag.
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

# What can sit on the x-axis: a timestamp, a numeric attribute, or a string.
XAxisValue = datetime | str | float


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
    x_attr_key: str | None = None,
    *,
    latest_only: bool = False,
) -> tuple[str, str, dict[str, list[tuple[XAxisValue, float]]]]:
    """Extract series per tag value for one metric from a metrics file.

    Args:
        path: path to the metrics export file (one or more JSON documents).
        metric_name: metric to read; defaults to the first metric found.
        attr_key: attribute used to split series (one line per distinct value);
            defaults to the first attribute key found on a data point.
        x_attr_key: attribute whose value is used as the x-axis coordinate.
            When set, the series identity is the combination of `attr_key` and
            `x_attr_key` values (labels join the values with '|'); otherwise the
            export timestamp is used as the x-axis and one series is drawn per
            `attr_key` value.
        latest_only: when True, keep only the points exported at the latest
            timestamp per series. The filter is applied on the raw export
            timestamp (`time_unix_nano`), regardless of the x-axis used.

    Returns:
        A tuple of (metric_name, attr_key, series) where `series` maps each tag
        value to a list of `(x_value, value)` pairs sorted by x_value. When
        `x_attr_key` is not set, `x_value` is a timezone-aware datetime.

    Raises:
        ObservabilityError: when no matching metric is found.
    """
    text = Path(path).read_text(encoding="utf-8")

    resolved_name: str | None = None
    resolved_attr = attr_key
    # Internal staging keeps the raw export timestamp so that `latest_only` can
    # filter on it even when the x-axis is taken from a tag instead.
    staged: dict[str, list[tuple[int, XAxisValue, float]]] = {}

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
                        label_keys = (resolved_attr,) + ((x_attr_key,) if x_attr_key is not None else ())
                        label = "|".join(
                            str(attributes.get(key, "?"))
                            for key in label_keys
                        )
                        timestamp = int(point["time_unix_nano"])
                        if x_attr_key is not None:
                            raw_x = attributes.get(x_attr_key, "?")
                            if isinstance(raw_x, bool):
                                x_value: XAxisValue = str(raw_x)
                            elif isinstance(raw_x, int | float):
                                x_value = float(raw_x)
                            else:
                                x_value = str(raw_x)
                        else:
                            x_value = datetime.fromtimestamp(timestamp / 1_000_000_000, tz=UTC)
                        staged.setdefault(label, []).append((timestamp, x_value, float(point["value"])))

    if resolved_name is None:
        error_message = f"no matching metric found in {path}"
        raise ObservabilityError(error_message)

    series: dict[str, list[tuple[XAxisValue, float]]] = {}
    for label, staged_points in staged.items():
        if latest_only:
            latest = max(timestamp for timestamp, _, _ in staged_points)
            picked_points = [point for point in staged_points if point[0] == latest]
        else:
            picked_points = staged_points
        extracted = [(x_value, value) for _, x_value, value in picked_points]
        extracted.sort(key=lambda item: item[0])
        series[label] = extracted

    return resolved_name, resolved_attr or "index", series


def plot_metric(
    path: str | Path,
    metric_name: str | None = None,
    attr_key: str | None = None,
    save_path: str | Path | None = None,
    x_attr_key: str | None = None,
    *,
    latest_only: bool = False,
) -> str | None:
    """Read a metrics export file and plot a metric as series of lines.

    Draws one line per tag (attribute) value (`attr_key`). By default the x-axis
    is the export timestamp; when `x_attr_key` is provided, the x-axis is taken
    from the value of that tag instead, and one line is drawn for each value of
    `attr_key` across the distinct `x_attr_key` values.

    Args:
        path: path to the metrics export file.
        metric_name: metric to plot; defaults to the first metric found.
        attr_key: attribute used to split series; defaults to the first found.
        x_attr_key: attribute whose value is used as the x-axis; when set, the
            export timestamp is ignored and the series identity is the
            combination of `attr_key` and `x_attr_key` values (labels join the
            values with '|'). Defaults to the timestamp.
        latest_only: when True, keep only the points exported at the latest
            timestamp per series. The filter is applied on the raw export
            timestamp (`time_unix_nano`), regardless of the x-axis used.
        save_path: when set, the figure is written here and the path returned;
            otherwise the figure is shown interactively and `None` is returned.

    Returns:
        The saved file path (as a string) when `save_path` is provided, else
        `None`.

    Example:
        uv run python -c "from tgedr_observability.plot import plot_metric; plot_metric('../fda_faers/otel/metrics','new_rows', 'table', save_path='output.png')"

    Example (x-axis from a tag):
        # x-axis = 'day' tag, one line per 'table' tag.
        uv run python -c "from tgedr_observability.plot import plot_metric; plot_metric('../fda_faers/otel/metrics','new_rows', attr_key='table', x_attr_key='day', save_path='output.png')"

    Example (latest point per tag only):
        # one point per table tag, taken from the most recent export.
        uv run python -c "from tgedr_observability.plot import plot_metric; plot_metric('../fda_faers/otel/metrics','new_rows', attr_key='table', latest_only=True, save_path='output.png')"
    """
    resolved_name, resolved_attr, series = load_metric_series(
        path,
        metric_name,
        attr_key,
        x_attr_key,
        latest_only=latest_only,
    )

    fig, ax = plt.subplots(figsize=(9, 5))
    for label in sorted(series):
        points = series[label]
        x_values = [x for x, _ in points]
        values = [value for _, value in points]
        ax.plot(x_values, values, marker="o", linewidth=2, label=label)

    ax.set_ylabel(resolved_name)
    if x_attr_key is not None:
        ax.set_title(f"{resolved_name} by {x_attr_key}")
        ax.set_xlabel(x_attr_key)
    else:
        ax.set_title(f"{resolved_name} over time")
        ax.set_xlabel("timestamp")
    legend_keys = (resolved_attr,) + ((x_attr_key,) if x_attr_key is not None else ())
    ax.legend(title=", ".join(legend_keys))
    ax.grid(visible=True, linestyle="--", alpha=0.4)
    if x_attr_key is None:
        fig.autofmt_xdate()
    fig.tight_layout()

    if save_path is not None:
        fig.savefig(save_path, dpi=120)
        plt.close(fig)
        return str(save_path)

    plt.show()
    plt.close(fig)
    return None
