"""Unit tests for commons module configuration helpers."""

from datetime import datetime, timezone
import os
from pathlib import Path

from tgedr_observability.commons import (
    DEFAULT_SERVICE_NAME,
    ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT,
    ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION,
    ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS,
    ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_LOGS_FILE,
    ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_METRICS_FILE,
    ENV_VAR_TGEDR_OBSERVABILITY_SERVICE,
    DayOfYearRotatingFile,
    OtlpConfig,
    day_of_year_path,
)


def test_resolve_from_env_without_endpoint_uses_defaults(monkeypatch) -> None:
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_SERVICE, "test-service")
    monkeypatch.delenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT, raising=False)
    monkeypatch.delenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS, raising=False)

    config = OtlpConfig.resolve_from_env()

    assert config is not None
    assert config.service == "test-service"
    assert config.http_exporter_endpoint is None


def test_resolve_from_env_without_service_uses_default(monkeypatch) -> None:
    monkeypatch.delenv(ENV_VAR_TGEDR_OBSERVABILITY_SERVICE, raising=False)
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT, "http://localhost:4318/v1/metrics")
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS, '{"Authorization": "Bearer token"}')

    config = OtlpConfig.resolve_from_env()

    assert config is not None
    assert config.service == DEFAULT_SERVICE_NAME


def test_otlp_config_defaults_service(monkeypatch) -> None:
    assert OtlpConfig().service == DEFAULT_SERVICE_NAME


def test_resolve_from_env_with_endpoint_and_headers(monkeypatch) -> None:
    endpoint = "http://localhost:4318/v1/metrics"
    headers_json = '{"Authorization": "Bearer token", "x-scope": "test"}'

    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_SERVICE, "test-service")
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT, endpoint)
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS, headers_json)

    config = OtlpConfig.resolve_from_env()

    assert config is not None
    assert config.service == "test-service"
    assert config.http_exporter_endpoint == endpoint
    assert config.http_exporter_headers == {"Authorization": "Bearer token", "x-scope": "test"}
    assert config.metrics_file_exporter_url is None
    assert config.logs_file_exporter_url is None


def test_resolve_from_env_with_file_exporters(monkeypatch) -> None:
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_SERVICE, "test-service")
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT, "http://localhost:4318/v1/metrics")
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_METRICS_FILE, "/tmp/metrics.log")
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_LOGS_FILE, "/tmp/logs.log")

    config = OtlpConfig.resolve_from_env()

    assert config is not None
    assert config.metrics_file_exporter_url == "/tmp/metrics.log"
    assert config.logs_file_exporter_url == "/tmp/logs.log"
    assert config.file_exporter_rotation is False


def test_resolve_from_env_file_rotation_flag(monkeypatch) -> None:
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT, "http://localhost:4318/v1/metrics")
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION, "true")
    assert OtlpConfig.resolve_from_env().file_exporter_rotation is True

    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION, "0")
    assert OtlpConfig.resolve_from_env().file_exporter_rotation is False

    monkeypatch.delenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION, raising=False)
    assert OtlpConfig.resolve_from_env().file_exporter_rotation is False


def test_day_of_year_path() -> None:
    when = datetime(2024, 1, 1, tzinfo=timezone.utc)  # day 001
    assert day_of_year_path("/var/log/app/metrics.log", when).name == "metrics.001.log"

    leap_day = datetime(2024, 12, 31, tzinfo=timezone.utc)  # day 366 (leap year)
    assert day_of_year_path("/var/log/app/metrics.log", leap_day).name == "metrics.366.log"


def test_rotating_file_writes_to_day_file(tmp_path: Path) -> None:
    base = tmp_path / "metrics.log"
    rotating = DayOfYearRotatingFile(base)

    rotating.write("hello")
    rotating.flush()

    today = datetime.now(tz=timezone.utc).timetuple().tm_yday
    target = tmp_path / f"metrics.{today:03d}.log"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "hello"

    # second write reuses the same handle (same day)
    rotating.write(" world")
    rotating.close()
    assert target.read_text(encoding="utf-8") == "hello world"
    assert rotating.closed is True


def test_rotating_file_overwrites_stale_previous_year(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "metrics.log"
    now = datetime(2025, 3, 1, tzinfo=timezone.utc)  # day 060
    monkeypatch.setattr("tgedr_observability.commons.datetime", _FakeDatetime(now))

    stale = tmp_path / "metrics.060.log"
    stale.write_text("last-year-data", encoding="utf-8")
    prev_year_ts = datetime(2024, 3, 1, tzinfo=timezone.utc).timestamp()
    os.utime(stale, (prev_year_ts, prev_year_ts))

    rotating = DayOfYearRotatingFile(base)
    rotating.write("fresh")
    rotating.close()

    assert stale.read_text(encoding="utf-8") == "fresh"


def test_rotating_file_appends_same_year(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "metrics.log"
    now = datetime(2025, 3, 1, tzinfo=timezone.utc)  # day 060
    monkeypatch.setattr("tgedr_observability.commons.datetime", _FakeDatetime(now))

    existing = tmp_path / "metrics.060.log"
    existing.write_text("earlier-today", encoding="utf-8")
    same_year_ts = datetime(2025, 3, 1, 6, tzinfo=timezone.utc).timestamp()
    os.utime(existing, (same_year_ts, same_year_ts))

    rotating = DayOfYearRotatingFile(base)
    rotating.write("-more")
    rotating.close()

    assert existing.read_text(encoding="utf-8") == "earlier-today-more"


def test_rotating_file_rotates_on_day_change(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "metrics.log"
    day1 = datetime(2025, 3, 1, tzinfo=timezone.utc)  # day 060
    day2 = datetime(2025, 3, 2, tzinfo=timezone.utc)  # day 061
    monkeypatch.setattr("tgedr_observability.commons.datetime", _FakeDatetime([day1, day2]))

    rotating = DayOfYearRotatingFile(base)
    rotating.write("day-one")  # uses day1 -> metrics.060.log
    rotating.write("day-two")  # uses day2 -> rotates, closes old handle, metrics.061.log
    rotating.close()

    assert (tmp_path / "metrics.060.log").read_text(encoding="utf-8") == "day-one"
    assert (tmp_path / "metrics.061.log").read_text(encoding="utf-8") == "day-two"


def test_rotating_file_close_idempotent(tmp_path: Path) -> None:
    rotating = DayOfYearRotatingFile(tmp_path / "metrics.log")
    # close before any write should not raise
    rotating.close()
    rotating.close()
    assert rotating.closed is True


class _FakeDatetime:
    """Stand-in for the `datetime` class with a scripted `now()`."""

    def __init__(self, fixed: datetime | list[datetime]) -> None:
        self._queue = list(fixed) if isinstance(fixed, list) else None
        self._fixed = None if isinstance(fixed, list) else fixed

    def now(self, tz=None) -> datetime:  # noqa: ANN001, ARG002
        if self._queue is not None:
            return self._queue.pop(0) if len(self._queue) > 1 else self._queue[0]
        return self._fixed  # pyright: ignore[reportReturnType]

    @staticmethod
    def fromtimestamp(timestamp: float, tz=None) -> datetime:  # noqa: ANN001
        return datetime.fromtimestamp(timestamp, tz=tz)
