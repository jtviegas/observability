"""Module with example function unit test for description purposes."""

import logging
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import pytest
from opentelemetry._logs import get_logger_provider

from tgedr_observability.commons import (
    ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT,
    ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_FILE,
    ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS,
    ENV_VAR_TGEDR_OBSERVABILITY_SERVICE,
)
from tgedr_observability.logs import Logs


SERVICE_NAME = "test_service"
LOCAL_LOGS_URL = "http://localhost:4318/v1/logs"


@pytest.fixture(scope="module", autouse=True)
def module_lifecycle():
    original_service = os.environ.get(ENV_VAR_TGEDR_OBSERVABILITY_SERVICE)
    original_endpoint = os.environ.get(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT)
    original_headers = os.environ.get(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS)

    _tmpdir = tempfile.TemporaryDirectory()
    os.environ[ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_FILE] = os.path.join(_tmpdir.name, "metrics.log")
    os.environ[ENV_VAR_TGEDR_OBSERVABILITY_SERVICE] = SERVICE_NAME
    os.environ[ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT] = LOCAL_LOGS_URL
    os.environ.pop(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS, None)


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

    if original_service is None:
        os.environ.pop(ENV_VAR_TGEDR_OBSERVABILITY_SERVICE, None)
    else:
        os.environ[ENV_VAR_TGEDR_OBSERVABILITY_SERVICE] = original_service

    if original_endpoint is None:
        os.environ.pop(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT, None)
    else:
        os.environ[ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT] = original_endpoint

    if original_headers is None:
        os.environ.pop(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS, None)
    else:
        os.environ[ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS] = original_headers

    os.environ.pop(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_FILE, None)

def test_logger(module_lifecycle) -> None:

    Logs.instance()
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.info("This is an OpenTelemetry log record!")

    flushed = get_logger_provider().force_flush(10000) # type: ignore
    assert flushed is True

    log_file = Path(os.getenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_FILE)) # pyright: ignore[reportArgumentType]
    content = log_file.read_text(encoding="utf-8")
    assert "This is an OpenTelemetry log record!" in content


def test_logs_lifecycle_methods(module_lifecycle) -> None:
    o: Logs = Logs.instance() # pyright: ignore[reportAssignmentType]
    o.shutdown()

    assert o.force_flush() is False
    o.shutdown()

    Logs.instance()
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
    o: Logs = Logs.instance() # pyright: ignore[reportAssignmentType]
    o.shutdown()
    Logs.app_shutdown()

    Logs.instance()
    logging.getLogger(__name__).info("logs app shutdown path")
    Logs.app_shutdown()
    assert o._logger_provider is None


def test_logs_app_shutdown_early_return(monkeypatch) -> None:
    monkeypatch.setattr(Logs, "instance", staticmethod(lambda: None))

    # Should return cleanly when provider is not initialized.
    Logs.app_shutdown()
