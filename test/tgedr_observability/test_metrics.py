"""Module with example function unit test for description purposes."""

import os
import signal
import subprocess
import time
import pytest
from opentelemetry import metrics as otel_metrics

from tgedr_observability.commons import LOCAL_METRICS_URL, ObservabilityError
from tgedr_observability.metrics import Metrics, OtlpConfig


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

def test_counter(module_lifecycle, capfd) -> None:

    o: Metrics = Metrics.instance()
    o.init(service="test_service", otlp_config=OtlpConfig(endpoint=LOCAL_METRICS_URL))
    o.add_to_counter("test.example.counter", 1, attributes={"key": "value"})

    # Force synchronous export so ConsoleMetricExporter output is available now.
    otel_metrics.get_meter_provider().force_flush() # type: ignore

    captured = capfd.readouterr()
    assert "Counter metric for test.example.counter" in captured.out
    assert '"value": 1' in captured.out

def test_gauge(module_lifecycle, capfd) -> None:

    o: Metrics = Metrics.instance()
    o.init(service="test_service", otlp_config=OtlpConfig(endpoint=LOCAL_METRICS_URL))
    o.add_to_gauge("test.example.gauge", 3.14, attributes={"key": "value"})

    otel_metrics.get_meter_provider().force_flush() # type: ignore
    captured = capfd.readouterr()
    assert "Gauge metric for test.example.gauge" in captured.out
    assert '"value": 3.14' in captured.out

def test_gauge_s(module_lifecycle, capfd) -> None:

    o: Metrics = Metrics.instance()
    o.init(service="test_service", otlp_config=OtlpConfig(endpoint=LOCAL_METRICS_URL))
    o.add_to_gauge("test.example.gauge_s", 173123123, attributes={"key": "value"})

    otel_metrics.get_meter_provider().force_flush() # type: ignore
    captured = capfd.readouterr()
    assert "Gauge metric for test.example.gauge_s" in captured.out
    assert '"value": 173123123' in captured.out

def test_histogram(module_lifecycle, capfd) -> None:

    o: Metrics = Metrics.instance()
    o.init(service="test_service", otlp_config=OtlpConfig(endpoint=LOCAL_METRICS_URL))
    for i in range(12):
        o.add_to_histogram("test.example.histogram", 42*i, attributes={"key": str(i)})

    otel_metrics.get_meter_provider().force_flush() # type: ignore
    captured = capfd.readouterr()
    assert "Histogram metric for test.example.histogram" in captured.out
    assert '"key": "11"' in captured.out

def test_histogram_s(module_lifecycle, capfd) -> None:

    o: Metrics = Metrics.instance()
    o.init(service="test_service", otlp_config=OtlpConfig(endpoint=LOCAL_METRICS_URL))
    for i in range(12):
        o.add_to_histogram("test.example.histogram_s", 173123123+i, attributes={"key": str(i)})

    otel_metrics.get_meter_provider().force_flush() # type: ignore
    captured = capfd.readouterr()
    assert "Histogram metric for test.example.histogram_s" in captured.out
    assert '"key": "11"' in captured.out


def test_invalid_metric_name_raises_value_error(module_lifecycle) -> None:
    o: Metrics = Metrics.instance()
    o.init(service="test_service", otlp_config=OtlpConfig(endpoint=LOCAL_METRICS_URL))

    with pytest.raises(ObservabilityError, match="at least two parts"):
        o.add_to_counter("counter", 1)


def test_metrics_lifecycle_methods(module_lifecycle) -> None:
    o: Metrics = Metrics.instance()
    o.shutdown()

    with pytest.raises(ObservabilityError, match="not initialized"):
        o.force_flush()

    o.init(service="test_service")
    o.add_to_counter("test.lifecycle.counter", 1)
    assert o.force_flush(10_000) is True

    o.shutdown()
    assert o._meter_provider is None
    assert o._meters == {}
    assert o._counters == {}
    assert o._gauges == {}
    assert o._histograms == {}


def test_metrics_app_shutdown(module_lifecycle) -> None:
    o: Metrics = Metrics.instance()
    o.shutdown()
    Metrics.app_shutdown()

    o.init(service="test_service")
    o.add_to_gauge("test.lifecycle.gauge", 1.0)
    Metrics.app_shutdown()
    assert o._meter_provider is None
