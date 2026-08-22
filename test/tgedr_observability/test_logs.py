"""Module with example function unit test for description purposes."""

import logging
import os
import signal
import subprocess
import time
import pytest
from opentelemetry._logs import get_logger_provider

from tgedr_observability.commons import LOCAL_METRICS_URL
from tgedr_observability.logs import Logs
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

def test_logger(module_lifecycle, capfd) -> None:

    Logs.instance().init(service="test_service", otlp_config=OtlpConfig(endpoint=LOCAL_METRICS_URL))
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.info("This is an OpenTelemetry log record!")

    flushed = get_logger_provider().force_flush(10000) # type: ignore
    assert flushed is True

    captured = capfd.readouterr()
    combined = captured.out + captured.err
    assert "This is an OpenTelemetry log record!" in combined


def test_logs_lifecycle_methods(module_lifecycle) -> None:
    o = Logs.instance()
    o.shutdown()

    assert o.force_flush() is False
    o.shutdown()

    o.init(service="test_service")
    assert o.force_flush(10_000) is True

    assert o._handler is not None
    handler = o._handler
    root_logger = logging.getLogger()
    assert any(existing is handler for existing in root_logger.handlers)

    o.shutdown()
    assert o._logger_provider is None
    assert o._handler is None
    assert all(existing is not handler for existing in root_logger.handlers)


def test_logs_app_shutdown(module_lifecycle) -> None:
    o = Logs.instance()
    o.shutdown()
    Logs.app_shutdown()

    o.init(service="test_service")
    logging.getLogger(__name__).info("logs app shutdown path")
    Logs.app_shutdown()
    assert o._logger_provider is None
