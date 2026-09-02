# tgedr-observability

![Coverage](./coverage.svg)
[![PyPI](https://img.shields.io/pypi/v/tgedr-observability)](https://pypi.org/project/tgedr-observability/)

## overview

This repository is an early-stage observability toolkit built around a small Python package and a companion local monitoring stack. The Docker side is the main operational surface: an OpenTelemetry collector receives telemetry and routes metrics, logs, and traces into dedicated backends for storage and analysis. In practice, the project acts as a foundation for collecting, storing, and exploring observability data rather than as a finished application.

## development
- main requirements:
  - _uv_  
  - _bash_
- Clone the repository like this:

  ``` bash
  git clone git@github.com:jtviegas/observability
  ```
- cd into the folder: `cd observability`
- install requirements: `./helper.sh reqs`

## source code guide

The Python package lives under `src/tgedr_observability` and currently exposes these modules:

- `commons.py`: shared constants and common types.
- `metrics.py`: singleton wrapper for OpenTelemetry metrics setup and recording.
- `logs.py`: singleton wrapper for OpenTelemetry logs setup and recording.
- `plot.py`: helpers to read an exported metrics file and plot a metric as a line graph.

### commons.py

`commons.py` contains:

- `LOCAL_METRICS_URL`: default local OTLP HTTP endpoint for metrics (`http://localhost:4318/v1/metrics`).
- OTLP environment variable names:
  - `TGEDR_OBSERVABILITY_SERVICE`
  - `TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT`
  - `TGEDR_OBSERVABILITY_EXPORTER_HEADERS`
  - `TGEDR_OBSERVABILITY_EXPORTER_METRICS_FILE`
  - `TGEDR_OBSERVABILITY_EXPORTER_LOGS_FILE`
  - `TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION_DAYS`
- `OtlpConfig`: frozen dataclass with `service` (defaults to `"observability"`), optional `http_exporter_endpoint`, optional `http_exporter_headers`, optional `metrics_file_exporter_url`, optional `logs_file_exporter_url`, and `file_rotation_days` (optional positive integer, defaults to `None`).
- `OtlpConfig.resolve_from_env()`: helper that builds an `OtlpConfig` from env vars.
  - `service` falls back to `"observability"` when `TGEDR_OBSERVABILITY_SERVICE` is not set.
  - Parses headers from JSON when provided.
  - Includes `metrics_file_exporter_url` from `TGEDR_OBSERVABILITY_EXPORTER_METRICS_FILE` and `logs_file_exporter_url` from `TGEDR_OBSERVABILITY_EXPORTER_LOGS_FILE` when set.
  - Sets `file_rotation_days` to positive `int` when `TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION_DAYS` is set.
- `file exporter rotation`: when `file_rotation_days` is set, file exporters write to a dated variant of the configured path in `YYYYMMDD` format (e.g. `metrics.log` -> `metrics.20260829.log`). When creating a new day's file, files older than `file_rotation_days` are automatically deleted. Helpers `dated_path()` and `DayOfYearRotatingFile` implement this.
- `ObservabilityError`: package-specific exception used for observability validation errors.

### metrics.py

`Metrics` is a singleton manager that lazily initializes a global OpenTelemetry `MeterProvider`.

Bootstrap behavior:

1. `Metrics.instance(otlp_config=None)` returns the singleton object when bootstrap succeeds.
2. If the provider is not initialized yet, `instance()` resolves configuration in this order:
  - explicit `otlp_config` argument, then
  - `OtlpConfig.resolve_from_env()`.
3. When a config is available, private method `__bootstrap(otlp_config)` runs and configures:
  - `Resource` with `service.name` from `otlp_config.service`.
  - `ConsoleMetricExporter` through a `PeriodicExportingMetricReader` (always enabled).
  - Optional file exporter (`ConsoleMetricExporter` writing to a file) when `otlp_config.metrics_file_exporter_url` is set. The parent directory is created automatically.
  - Optional OTLP HTTP exporter (`OTLPMetricExporter`) when `otlp_config.http_exporter_endpoint` is set.
4. The configured provider is installed globally with `metrics.set_meter_provider(provider)`.
5. If no config can be resolved, `instance()` returns `None`.

Metric naming convention:

- Metric names must have at least two dot-separated parts, for example `orders.api.requests`.
- Everything before the last segment is used as meter scope name.
- Last segment is used as instrument name.
- Invalid names raise `ObservabilityError`.

Instruments managed by the class:

- Counter path: internally uses `create_up_down_counter`.
- Gauge path: uses `create_gauge` with unit inferred from suffix (`_s` -> `s`, otherwise `1`).
- Histogram path: uses `create_histogram` with the same unit inference.

Public methods:

- `add_to_counter(name, value, attributes=None)`
- `add_to_gauge(name, value, attributes=None)`
- `add_to_histogram(name, value, attributes=None)`
- `force_flush(timeout_millis=10000)`
- `shutdown()`
- `app_shutdown()` (flush + shutdown convenience hook; no-op if `instance()` resolves to `None`)

### logs.py

`Logs` is a singleton manager that lazily initializes a global OpenTelemetry `LoggerProvider`.

Bootstrap behavior:

1. `Logs.instance(otlp_config=None)` returns the singleton object when bootstrap succeeds.
2. If the provider is not initialized yet, `instance()` resolves configuration in this order:
  - explicit `otlp_config` argument, then
  - `OtlpConfig.resolve_from_env()`.
3. When a config is available, private method `__bootstrap(otlp_config)` runs and configures:
  - `Resource` with `service.name` from `otlp_config.service`.
  - `BatchLogRecordProcessor(ConsoleLogRecordExporter())` (always enabled).
  - Optional file exporter (`ConsoleLogRecordExporter` writing to a file) when `otlp_config.logs_file_exporter_url` is set. The parent directory is created automatically.
  - Optional `BatchLogRecordProcessor(OTLPLogExporter(...))` when `otlp_config.http_exporter_endpoint` is set.
4. The provider is installed globally with `set_logger_provider(provider)`.
5. `LoggingHandler` is attached through `logging.basicConfig(..., force=True)`.
6. If no config can be resolved, `instance()` returns `None`.

Public methods:

- `force_flush(timeout_millis=10000)`
- `shutdown()` (also detaches and closes the installed handler)
- `app_shutdown()` (flush + shutdown convenience hook; no-op if `instance()` resolves to `None`)

### plot.py

`plot.py` reads a metrics export file produced by the file exporter
(`ConsoleMetricExporter` output — one JSON document per flush, appended to the
file) and renders a metric as a line graph across its tag (attribute) values.

Functions:

- `load_metric_series(path, metric_name=None, attr_key=None, x_attr_key=None, *, latest_only=False)`:
  returns `(metric_name, attr_key, series)` where `series` maps each tag value
  (or combination of `attr_key` + `x_attr_key`, when the latter is set) to a
  list of `(x_value, value)` pairs sorted by `x_value`. By default the x-axis
  is the export timestamp; when `x_attr_key` is set, the x-axis is taken from
  the value of that tag instead and the series identity becomes the combination
  of both tags (labels join the values with `|`, and the legend title lists the
  keys). Handles files with multiple concatenated JSON documents. When
  `latest_only` is True, only the points exported at the latest timestamp are
  kept per series. Defaults to the first metric / first attribute found. Raises
  `ObservabilityError` when no matching metric is found.
- `plot_metric(path, metric_name=None, attr_key=None, save_path=None, x_attr_key=None, *, latest_only=False)`:
  draws one line per tag value (or per combination when `x_attr_key` is set)
  and renders the graph. When `save_path` is set, the figure is written there
  and the path returned; otherwise the figure is shown and `None` is returned.
  Uses a non-interactive backend so it is safe in headless/CI environments.

Example:

```python
from tgedr_observability.plot import plot_metric

# save to a file
plot_metric("/var/log/myapp/metrics.log", save_path="new_rows.png")

# or show interactively, choosing a specific metric and tag
plot_metric("/var/log/myapp/metrics.log", metric_name="new_rows", attr_key="table")

# plot only the most recent export per tag value
plot_metric("/var/log/myapp/metrics.log", metric_name="new_rows", attr_key="table", latest_only=True)

# plot the most recent export per tag combination (table + day)
plot_metric("/var/log/myapp/metrics.log", metric_name="new_rows", attr_key="table", x_attr_key="day", latest_only=True)
```

## usage examples

You can bootstrap in two ways:

- Pass an explicit `OtlpConfig` to `Metrics.instance(...)` / `Logs.instance(...)`.
- Set environment variables and let `instance()` load config automatically.

Environment-only bootstrap requires:

- Optional `TGEDR_OBSERVABILITY_SERVICE` (defaults to `observability` when unset)
- `TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT`
- Optional `TGEDR_OBSERVABILITY_EXPORTER_HEADERS` as a JSON object string.
- Optional `TGEDR_OBSERVABILITY_EXPORTER_METRICS_FILE` — path to a file where metrics are also written (used by `Metrics`; parent directories are created automatically).
- Optional `TGEDR_OBSERVABILITY_EXPORTER_LOGS_FILE` — path to a file where logs are also written (used by `Logs`; parent directories are created automatically).
- Optional `TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION_DAYS` — set to a positive integer (e.g. `7`, `30`) to enable daily rotation with automatic cleanup of files older than that number of days (`YYYYMMDD` format, e.g. `metrics.20260829.log`).

Example:

```bash
export TGEDR_OBSERVABILITY_SERVICE="orders-service"
export TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT="http://localhost:4318/v1/metrics"
export TGEDR_OBSERVABILITY_EXPORTER_HEADERS='{"Authorization":"Bearer your-token"}'
export TGEDR_OBSERVABILITY_EXPORTER_METRICS_FILE="/var/log/myapp/metrics.log"
export TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION_DAYS="7"
```

For logs, use the logs endpoint in `TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT` and the logs file variable:

```bash
export TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT="http://localhost:4318/v1/logs"
export TGEDR_OBSERVABILITY_EXPORTER_LOGS_FILE="/var/log/myapp/logs.log"
export TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION_DAYS="7"
```

### metrics

```python
from tgedr_observability.commons import LOCAL_METRICS_URL, OtlpConfig
from tgedr_observability.metrics import Metrics

metrics_manager = Metrics.instance(
  otlp_config=OtlpConfig(service="orders-service", http_exporter_endpoint=LOCAL_METRICS_URL),
)
if metrics_manager is None:
  raise RuntimeError("Metrics bootstrap failed: missing config")

metrics_manager.add_to_counter("orders.api.requests", 1, {"route": "/orders"})
metrics_manager.add_to_histogram("orders.api.latency_s", 0.123, {"route": "/orders"})
metrics_manager.force_flush()
```

Metrics with file exporter:

```python
from tgedr_observability.commons import OtlpConfig
from tgedr_observability.metrics import Metrics

metrics_manager = Metrics.instance(
  otlp_config=OtlpConfig(
    service="orders-service",
    http_exporter_endpoint="http://localhost:4318/v1/metrics",
    metrics_file_exporter_url="/var/log/myapp/metrics.log",
    file_rotation_days=7,
  ),
)
if metrics_manager is None:
  raise RuntimeError("Metrics bootstrap failed: missing config")

metrics_manager.add_to_counter("orders.api.requests", 1, {"route": "/orders"})
metrics_manager.force_flush()
```

Metrics with environment-only bootstrap:

```python
from tgedr_observability.metrics import Metrics

metrics_manager = Metrics.instance()
if metrics_manager is None:
  raise RuntimeError("Metrics bootstrap failed: set TGEDR_OBSERVABILITY_* env vars")

metrics_manager.add_to_counter("orders.api.requests", 1, {"route": "/orders"})
metrics_manager.force_flush()
```

### logs

```python
import logging
from tgedr_observability.commons import OtlpConfig
from tgedr_observability.logs import Logs

logs_manager = Logs.instance(
  otlp_config=OtlpConfig(service="orders-service", http_exporter_endpoint="http://localhost:4318/v1/logs"),
)
if logs_manager is None:
  raise RuntimeError("Logs bootstrap failed: missing config")

logger = logging.getLogger(__name__)
logger.info("orders api started")
logs_manager.force_flush()
```

Logs with file exporter:

```python
import logging
from tgedr_observability.commons import OtlpConfig
from tgedr_observability.logs import Logs

logs_manager = Logs.instance(
  otlp_config=OtlpConfig(
    service="orders-service",
    http_exporter_endpoint="http://localhost:4318/v1/logs",
    logs_file_exporter_url="/var/log/myapp/logs.log",
    file_rotation_days=7,
  ),
)
if logs_manager is None:
  raise RuntimeError("Logs bootstrap failed: missing config")

logger = logging.getLogger(__name__)
logger.info("orders api started")
logs_manager.force_flush()
```

Logs with environment-only bootstrap:

```python
import logging
from tgedr_observability.logs import Logs

logs_manager = Logs.instance()
if logs_manager is None:
  raise RuntimeError("Logs bootstrap failed: set TGEDR_OBSERVABILITY_* env vars")

logger = logging.getLogger(__name__)
logger.info("orders api started")
logs_manager.force_flush()
```

### graceful shutdown

Register app-level shutdown hooks in your entrypoint:

```python
import atexit
from tgedr_observability.logs import Logs
from tgedr_observability.metrics import Metrics

atexit.register(Logs.app_shutdown)
atexit.register(Metrics.app_shutdown)
```

## tests and coverage

Run tests:

```bash
./helper.sh test
```

Run and print coverage:

```bash
./helper.sh test_coverage
```

Current unit tests cover all Python code under `src/`.


## observability stack

### VictoriaMetrics

`victoriametrics/victoria-metrics` is the metrics database in this stack. It stores time-series data such as request counts, latency measurements, resource usage, and any custom application metrics sent through OpenTelemetry. In this project, the collector forwards metrics to VictoriaMetrics through its OpenTelemetry ingestion endpoint, and Grafana can then query that stored data for dashboards and operational analysis.

### Loki

`grafana/loki` is the log storage backend. Loki is designed to ingest and organize logs efficiently, making it a good fit for centralizing application and infrastructure logs without the overhead of a heavier full-text indexing platform. Here, the OpenTelemetry collector sends log data to Loki so logs can be explored alongside metrics and traces, which makes it easier to correlate failures, warnings, and service behavior across the same time window.

### Jaeger

`jaegertracing/all-in-one` is the distributed tracing backend. It collects and visualizes traces, which show how a request flows across services and how long each span takes, making it useful for debugging latency and request-path failures. The `all-in-one` image bundles Jaeger's main components into a single container, which keeps this setup simple for local or small-scale environments while still providing a usable trace exploration surface.

## securing the collector

**⚠️ Important: The collector requires a valid Bearer token on every request.** The OTLP HTTP receiver is protected with Bearer token authentication using the OpenTelemetry Collector's `bearertokenauth` extension. Any request to the collector endpoint (`localhost:4318` or the remote endpoint) without an `Authorization: Bearer <token>` header will be rejected with HTTP 401 Unauthorized. This applies to all telemetry data—traces, metrics, and logs.

### configuration

1. **Set the token.** Add a strong random secret to your `.secrets` file (which is git-ignored and loaded by `helper.sh`):

   ```bash
   export COLLECTOR_TOKEN="$(openssl rand -hex 32)"
   ```

2. **Rebuild and push the collector image** so the updated config is baked in:

   ```bash
   ./helper.sh build_push_collector
   ```

3. **Start the stack.** The `docker-compose.yml` passes `COLLECTOR_TOKEN` through as an environment variable so the collector reads it at runtime:

   ```bash
   cd docker/observability && docker compose up -d
   ```

### sending telemetry

**All telemetry ingestion requires the token header.** Any client sending OTLP over HTTP must include the `Authorization: Bearer <token>` header on every call, or the request will be rejected:

```
Authorization: Bearer <your-token>
```

**Examples:**

With `telemetrygen` (as used in `helper.sh`):

```bash
telemetrygen traces --otlp-http \
  --otlp-header "Authorization=\"Bearer $COLLECTOR_TOKEN\"" \
  --traces 1
```

With the OpenTelemetry SDK, configure the exporter headers via the `OTEL_EXPORTER_OTLP_HEADERS` environment variable (applied to all outbound requests):

```bash
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer $COLLECTOR_TOKEN"
```

If the token is missing or invalid, the collector will return `401 Unauthorized`. Verify the token is set correctly in your environment before troubleshooting other issues.
