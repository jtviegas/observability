"""Unit tests for commons module configuration helpers."""

from datetime import datetime, timezone
import os
from pathlib import Path

from tgedr_observability.commons import (
    DEFAULT_SERVICE_NAME,
    ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT,
    ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION_DAYS,
    ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS,
    ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_LOGS_FILE,
    ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_METRICS_FILE,
    ENV_VAR_TGEDR_OBSERVABILITY_SERVICE,
    DayOfYearRotatingFile,
    OtlpConfig,
    dated_path,
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
    assert config.file_rotation_days is None


def test_resolve_from_env_file_rotation_days(monkeypatch) -> None:
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT, "http://localhost:4318/v1/metrics")
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION_DAYS, "7")
    assert OtlpConfig.resolve_from_env().file_rotation_days == 7

    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION_DAYS, "0")
    assert OtlpConfig.resolve_from_env().file_rotation_days is None

    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION_DAYS, "-1")
    assert OtlpConfig.resolve_from_env().file_rotation_days is None

    monkeypatch.delenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION_DAYS, raising=False)
    assert OtlpConfig.resolve_from_env().file_rotation_days is None

    # Test with invalid value
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION_DAYS, "invalid")
    assert OtlpConfig.resolve_from_env().file_rotation_days is None


def test_dated_path() -> None:
    when = datetime(2026, 8, 29, tzinfo=timezone.utc)  # YYYYMMDD: 20260829
    assert dated_path("/var/log/app/metrics.log", when).name == "metrics.20260829.log"

    when = datetime(2026, 1, 1, tzinfo=timezone.utc)  # YYYYMMDD: 20260101
    assert dated_path("/var/log/app/metrics.log", when).name == "metrics.20260101.log"


def test_rotating_file_writes_to_dated_file(tmp_path: Path) -> None:
    base = tmp_path / "metrics.log"
    rotating = DayOfYearRotatingFile(base)

    rotating.write("hello")
    rotating.flush()

    today = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    target = tmp_path / f"metrics.{today}.log"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "hello"

    # second write reuses the same handle (same day)
    rotating.write(" world")
    rotating.close()
    assert target.read_text(encoding="utf-8") == "hello world"
    assert rotating.closed is True


def test_rotating_file_overwrites_stale_previous_day(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "metrics.log"
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)  # 20260829
    yesterday = datetime(2026, 8, 28, tzinfo=timezone.utc)  # 20260828
    monkeypatch.setattr("tgedr_observability.commons.datetime", _FakeDatetime(now))

    # Create a file from yesterday
    old = tmp_path / "metrics.20260828.log"
    old.write_text("yesterday-data", encoding="utf-8")

    rotating = DayOfYearRotatingFile(base)
    rotating.write("fresh")
    rotating.close()

    # Old file should still exist (we only clean up based on retention_days)
    assert old.exists()
    assert old.read_text(encoding="utf-8") == "yesterday-data"
    
    # New file for today should be created
    today_file = tmp_path / "metrics.20260829.log"
    assert today_file.exists()
    assert today_file.read_text(encoding="utf-8") == "fresh"


def test_rotating_file_appends_same_day(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "metrics.log"
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)  # day 20260829
    monkeypatch.setattr("tgedr_observability.commons.datetime", _FakeDatetime(now))

    existing = tmp_path / "metrics.20260829.log"
    existing.write_text("earlier-today", encoding="utf-8")

    rotating = DayOfYearRotatingFile(base)
    rotating.write("-more")
    rotating.close()

    assert existing.read_text(encoding="utf-8") == "earlier-today-more"


def test_rotating_file_rotates_on_day_change(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "metrics.log"
    day1 = datetime(2026, 8, 28, tzinfo=timezone.utc)  # 20260828
    day2 = datetime(2026, 8, 29, tzinfo=timezone.utc)  # 20260829
    monkeypatch.setattr("tgedr_observability.commons.datetime", _FakeDatetime([day1, day2]))

    rotating = DayOfYearRotatingFile(base)
    rotating.write("day-one")  # uses day1 -> metrics.20260828.log
    rotating.write("day-two")  # uses day2 -> rotates, closes old handle, metrics.20260829.log
    rotating.close()

    assert (tmp_path / "metrics.20260828.log").read_text(encoding="utf-8") == "day-one"
    assert (tmp_path / "metrics.20260829.log").read_text(encoding="utf-8") == "day-two"


def test_rotating_file_close_idempotent(tmp_path: Path) -> None:
    rotating = DayOfYearRotatingFile(tmp_path / "metrics.log")
    # close before any write should not raise
    rotating.close()
    rotating.close()
    assert rotating.closed is True


def test_rotating_file_cleanup_old_files(tmp_path: Path, monkeypatch) -> None:
    """Test that old files are deleted when retention_days is set."""
    import datetime as dt
    
    base = tmp_path / "metrics.log"
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)  # 20260829
    monkeypatch.setattr("tgedr_observability.commons.datetime", _FakeDatetime(now))

    # Create files for the past 10 days
    for i in range(10):
        days_ago = 9 - i
        past_date = now - dt.timedelta(days=days_ago)
        past_date_str = past_date.strftime("%Y%m%d")
        file_path = tmp_path / f"metrics.{past_date_str}.log"
        file_path.write_text(f"data-{i}", encoding="utf-8")

    # Create rotating file with 7-day retention
    rotating = DayOfYearRotatingFile(base, retention_days=7)
    rotating.write("today-data")
    rotating.close()

    # Check that files older than 7 days are deleted
    remaining_files = list(tmp_path.glob("metrics.????????.log"))
    # With 7-day retention: keep today + past 7 days = 8 files
    assert len(remaining_files) == 8
    
    # Check that today's file exists
    today_file = tmp_path / "metrics.20260829.log"
    assert today_file.exists()


def test_rotating_file_cleanup_handles_unparseable_filenames(tmp_path: Path, monkeypatch) -> None:
    """Test that cleanup gracefully skips files with unparseable names."""
    import datetime as dt
    
    base = tmp_path / "metrics.log"
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)  # 20260829
    monkeypatch.setattr("tgedr_observability.commons.datetime", _FakeDatetime(now))

    # Create 3 days of valid files: 2 days ago, yesterday, today
    for i in range(3):
        days_ago = 2 - i
        past_date = now - dt.timedelta(days=days_ago)
        past_date_str = past_date.strftime("%Y%m%d")
        file_path = tmp_path / f"metrics.{past_date_str}.log"
        file_path.write_text(f"data-{i}", encoding="utf-8")

    # Create some files with non-date patterns of length 8 (should be skipped by isdigit check)
    (tmp_path / "metrics.abcdefgh.log").write_text("invalid-data", encoding="utf-8")

    # Create rotating file with 1-day retention
    rotating = DayOfYearRotatingFile(base, retention_days=1)
    rotating.write("today-data")
    rotating.close()

    # With 1-day retention: keep today (20260829) + yesterday (20260828) = 2 valid files
    # 2 days ago (20260827) should be deleted
    # The non-date file (metrics.abcdefgh.log) should remain intact
    valid_dated_files = list(tmp_path.glob("metrics.????????.log"))
    # 2 valid date files + 1 invalid name file = 3 files total with 8 chars
    assert len(valid_dated_files) == 3
    assert (tmp_path / "metrics.abcdefgh.log").exists()
    assert not (tmp_path / "metrics.20260827.log").exists()


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
