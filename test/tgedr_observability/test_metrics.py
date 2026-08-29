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
    return OtlpConfig(service=SERVICE_NAME, http_exporter_endpoint=LOCAL_METRICS_URL, metrics_file_exporter_url=_METRICS_LOG)

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

    o: Metrics = Metrics.instance(otlp_config=_otlp_config()) # pyright: ignore[reportAssignmentType]
    o.add_to_counter("test.example.counter", 1, attributes={"key": "value"})

    # Force synchronous export so ConsoleMetricExporter output is available now.
    assert otel_metrics.get_meter_provider().force_flush() is True # type: ignore

def test_counter_fileexport(module_lifecycle) -> None:

    o: Metrics = Metrics.instance(otlp_config=_otlp_config()) # pyright: ignore[reportAssignmentType]
    o.add_to_counter("test.fileexport.counter", 1, attributes={"key": "value"})
    assert o.force_flush() is True

    metrics_file = list(Path(_METRICS_LOG).parent.rglob("*.log"))[0]
    content = metrics_file.read_text(encoding="utf-8")
    assert "Counter metric for test.fileexport.counter" in content


def test_gauge(module_lifecycle) -> None:

    o: Metrics = Metrics.instance(otlp_config=_otlp_config()) # pyright: ignore[reportAssignmentType]
    o.add_to_gauge("test.example.gauge", 3.14, attributes={"key": "value"})

    assert otel_metrics.get_meter_provider().force_flush() is True # type: ignore

def test_gauge_s(module_lifecycle) -> None:

    o: Metrics = Metrics.instance(otlp_config=_otlp_config()) # pyright: ignore[reportAssignmentType]
    o.add_to_gauge("test.example.gauge_s", 173123123, attributes={"key": "value"})

    assert otel_metrics.get_meter_provider().force_flush() is True # type: ignore

def test_histogram(module_lifecycle) -> None:

    o: Metrics = Metrics.instance(otlp_config=_otlp_config()) # pyright: ignore[reportAssignmentType]
    for i in range(12):
        o.add_to_histogram("test.example.histogram", 42*i, attributes={"key": str(i)})

    assert otel_metrics.get_meter_provider().force_flush() is True # type: ignore

def test_histogram_s(module_lifecycle) -> None:

    o: Metrics = Metrics.instance(otlp_config=_otlp_config()) # pyright: ignore[reportAssignmentType]
    for i in range(12):
        o.add_to_histogram("test.example.histogram_s", 173123123+i, attributes={"key": str(i)})

    assert otel_metrics.get_meter_provider().force_flush() is True # type: ignore


def test_invalid_metric_name_raises_value_error(module_lifecycle) -> None:
    o: Metrics = Metrics.instance(otlp_config=_otlp_config()) # pyright: ignore[reportAssignmentType]

    with pytest.raises(ObservabilityError, match="at least two parts"):
        o.add_to_counter("counter", 1)


def test_metrics_lifecycle_methods(module_lifecycle) -> None:
    o: Metrics = Metrics() # pyright: ignore[reportAssignmentType]
    o.shutdown()

    with pytest.raises(ObservabilityError, match="not initialized"):
        o.force_flush()

    o = Metrics.instance(otlp_config=_otlp_config()) # pyright: ignore[reportAssignmentType]
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

    o: Metrics = Metrics() # pyright: ignore[reportAssignmentType]
    o.shutdown()
    Metrics.app_shutdown()

    o = Metrics.instance(otlp_config=_otlp_config()) # pyright: ignore[reportAssignmentType]
    o.add_to_gauge("test.lifecycle.gauge", 1.0)
    Metrics.app_shutdown()
    assert o._meter_provider is None


def test_metrics_instance_always_returns_instance(monkeypatch) -> None:
    monkeypatch.delenv(ENV_VAR_TGEDR_OBSERVABILITY_SERVICE, raising=False)
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT, LOCAL_METRICS_URL)

    o: Metrics = Metrics()  # pyright: ignore[reportAssignmentType]
    o.shutdown()

    instance = Metrics.instance()
    assert instance is not None
    assert instance._meter_provider is not None
    instance.shutdown()


def test_metrics_file_exporter_rotation(module_lifecycle) -> None:
    from datetime import datetime, timezone

    from tgedr_observability.commons import DayOfYearRotatingFile

    rotation_dir = tempfile.TemporaryDirectory()
    base_log = os.path.join(rotation_dir.name, "metrics.log")

    o: Metrics = Metrics()  # pyright: ignore[reportAssignmentType]
    o.shutdown()

    o = Metrics.instance(  # pyright: ignore[reportAssignmentType]
        otlp_config=OtlpConfig(
            service=SERVICE_NAME,
            metrics_file_exporter_url=base_log,
            file_rotation_days=7,
        )
    )
    assert isinstance(o._log_file, DayOfYearRotatingFile)
    # Global meter provider is set once per process; earlier tests may own it,
    # so exercise the wired rotating file directly to verify YYYYMMDD output.
    o._log_file.write("Counter metric for test.rotation.counter")
    o._log_file.flush()

    today = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    rotated = Path(rotation_dir.name) / f"metrics.{today}.log"
    assert rotated.exists()
    assert "Counter metric for test.rotation.counter" in rotated.read_text(encoding="utf-8")

    o.shutdown()
    assert o._log_file is None
    rotation_dir.cleanup()


def test_metrics_file_exporter_no_rotation(module_lifecycle) -> None:
    """Test file exporter with rotation disabled (file_rotation_days=None)."""
    no_rotation_dir = tempfile.TemporaryDirectory()
    base_log = os.path.join(no_rotation_dir.name, "metrics.log")

    o: Metrics = Metrics()  # pyright: ignore[reportAssignmentType]
    o.shutdown()

    o = Metrics.instance(  # pyright: ignore[reportAssignmentType]
        otlp_config=OtlpConfig(
            service=SERVICE_NAME,
            metrics_file_exporter_url=base_log,
            file_rotation_days=None,
        )
    )
    # When rotation is disabled, _log_file should be a regular file object
    assert hasattr(o._log_file, "write")
    assert hasattr(o._log_file, "flush")

    # Verify the file exists with the exact name (no date suffix)
    log_path = Path(base_log)
    assert log_path.exists()

    o._log_file.write("Gauge metric for test.no_rotation.gauge")
    o._log_file.flush()

    content = log_path.read_text(encoding="utf-8")
    assert "Gauge metric for test.no_rotation.gauge" in content

    o.shutdown()
    assert o._log_file is None
    no_rotation_dir.cleanup()
