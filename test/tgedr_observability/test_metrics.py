"""Module with example function unit test for description purposes."""

import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import pytest
from opentelemetry import metrics as otel_metrics

from tgedr_observability.commons import (
    ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT,
    ENV_VAR_TGEDR_OBSERVABILITY_SERVICE,
    LOCAL_METRICS_URL,
    ObservabilityError,
)
from tgedr_observability.metrics import Metrics, OtlpConfig


SERVICE_NAME = "test_service"
_metrics_tmpdir = tempfile.TemporaryDirectory()
_METRICS_LOG = os.path.join(_metrics_tmpdir.name, "metrics.log")


def _otlp_config() -> OtlpConfig:
    return OtlpConfig(service=SERVICE_NAME, http_exporter_endpoint=LOCAL_METRICS_URL, file_exporter_url=_METRICS_LOG)

@pytest.fixture(scope="module", autouse=True)
def module_lifecycle():
    # Start script in its own process group so teardown can kill children too
    proc = subprocess.Popen(
        ["bash", "helper.sh", "run_local_collector"],
        cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,  # creates new session/process group on Unix
    )

    print(f"setup.sh PID: {proc.pid}")

    # Optional: wait a bit or implement readiness check
    time.sleep(1)

    yield proc  # tests can receive this fixture and use proc.pid if needed

    # Teardown: terminate whole process group
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        # Process already exited
        pass

def test_counter(module_lifecycle) -> None:

    o: Metrics = Metrics.instance(otlp_config=_otlp_config())
    o.add_to_counter("test.example.counter", 1, attributes={"key": "value"})

    # Force synchronous export so ConsoleMetricExporter output is available now.
    assert otel_metrics.get_meter_provider().force_flush() is True # type: ignore

def test_counter_fileexport(module_lifecycle) -> None:

    o: Metrics = Metrics.instance(otlp_config=_otlp_config())
    o.add_to_counter("test.fileexport.counter", 1, attributes={"key": "value"})
    assert o.force_flush() is True

    log_file = Path(_METRICS_LOG)
    content = log_file.read_text(encoding="utf-8")
    assert "Counter metric for test.fileexport.counter" in content


def test_gauge(module_lifecycle) -> None:

    o: Metrics = Metrics.instance(otlp_config=_otlp_config())
    o.add_to_gauge("test.example.gauge", 3.14, attributes={"key": "value"})

    assert otel_metrics.get_meter_provider().force_flush() is True # type: ignore

def test_gauge_s(module_lifecycle) -> None:

    o: Metrics = Metrics.instance(otlp_config=_otlp_config())
    o.add_to_gauge("test.example.gauge_s", 173123123, attributes={"key": "value"})

    assert otel_metrics.get_meter_provider().force_flush() is True # type: ignore

def test_histogram(module_lifecycle) -> None:

    o: Metrics = Metrics.instance(otlp_config=_otlp_config())
    for i in range(12):
        o.add_to_histogram("test.example.histogram", 42*i, attributes={"key": str(i)})

    assert otel_metrics.get_meter_provider().force_flush() is True # type: ignore

def test_histogram_s(module_lifecycle) -> None:

    o: Metrics = Metrics.instance(otlp_config=_otlp_config())
    for i in range(12):
        o.add_to_histogram("test.example.histogram_s", 173123123+i, attributes={"key": str(i)})

    assert otel_metrics.get_meter_provider().force_flush() is True # type: ignore


def test_invalid_metric_name_raises_value_error(module_lifecycle) -> None:
    o: Metrics = Metrics.instance(otlp_config=_otlp_config())

    with pytest.raises(ObservabilityError, match="at least two parts"):
        o.add_to_counter("counter", 1)


def test_metrics_lifecycle_methods(module_lifecycle) -> None:
    o: Metrics = Metrics()
    o.shutdown()

    with pytest.raises(ObservabilityError, match="not initialized"):
        o.force_flush()

    o = Metrics.instance(otlp_config=_otlp_config())
    o.add_to_counter("test.lifecycle.counter", 1)
    assert o.force_flush(10_000) is True

    o.shutdown()
    assert o._meter_provider is None
    assert o._meters == {}
    assert o._counters == {}
    assert o._gauges == {}
    assert o._histograms == {}


def test_metrics_app_shutdown(module_lifecycle, monkeypatch) -> None:
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_SERVICE, SERVICE_NAME)
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT, LOCAL_METRICS_URL)

    o: Metrics = Metrics()
    o.shutdown()
    Metrics.app_shutdown()

    o = Metrics.instance(otlp_config=_otlp_config())
    o.add_to_gauge("test.lifecycle.gauge", 1.0)
    Metrics.app_shutdown()
    assert o._meter_provider is None


def test_metrics_app_shutdown_early_return(monkeypatch) -> None:
    monkeypatch.setattr(Metrics, "instance", staticmethod(lambda: None))

    # Should return cleanly when provider is not initialized.
    Metrics.app_shutdown()


def test_metrics_instance_returns_none_without_config(monkeypatch) -> None:
    monkeypatch.delenv(ENV_VAR_TGEDR_OBSERVABILITY_SERVICE, raising=False)
    monkeypatch.delenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT, raising=False)

    assert Metrics.instance() is None
