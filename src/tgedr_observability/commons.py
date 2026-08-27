"""Common configuration models for observability integrations."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import os
import json

LOCAL_METRICS_URL: str = "http://localhost:4318/v1/metrics"
DEFAULT_SERVICE_NAME: str = "observability"
ENV_VAR_TGEDR_OBSERVABILITY_SERVICE: str = "TGEDR_OBSERVABILITY_SERVICE"
ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT: str = "TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT"
ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS: str = "TGEDR_OBSERVABILITY_EXPORTER_HEADERS"
ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_METRICS_FILE: str = "TGEDR_OBSERVABILITY_EXPORTER_METRICS_FILE"
ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_LOGS_FILE: str = "TGEDR_OBSERVABILITY_EXPORTER_LOGS_FILE"
ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION: str = "TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION"


def _env_flag(name: str) -> bool:
    """Return True when the named env var holds a truthy value."""
    value = os.getenv(name)
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


def day_of_year_path(base_path: str | Path, when: datetime | None = None) -> Path:
    """Build a day-of-year variant of `base_path`.

    `/var/log/app/metrics.log` -> `/var/log/app/metrics.001.log` on Jan 1st.
    The day-of-year is zero-padded to three digits (`001`..`366`), giving a
    fixed set of filenames that repeat every year (yearly rotation).
    """
    moment = when or datetime.now(tz=UTC)
    day = moment.timetuple().tm_yday
    path = Path(base_path)
    return path.with_name(f"{path.stem}.{day:03d}{path.suffix}")


class DayOfYearRotatingFile:
    """Write-through text file that rotates by day-of-year (yearly rotation).

    Behaves like a writable text file for exporters that hold an `out` stream.
    On each write it targets `base_path` rewritten with the current day-of-year.
    When the target already exists but was last modified in a previous year, it
    is truncated first so stale data from the same day last year is discarded.
    """

    def __init__(self, base_path: str | Path, encoding: str = "utf-8") -> None:
        """Create the rotating file for the given base path."""
        self._base_path = Path(base_path)
        self._encoding = encoding
        self._current_path: Path | None = None
        self._handle = None
        self.closed = False

    def _ensure_handle(self, when: datetime | None = None) -> None:
        target = day_of_year_path(self._base_path, when)
        if self._handle is not None and self._current_path == target and not self._handle.closed:
            return

        if self._handle is not None and not self._handle.closed:
            self._handle.close()

        target.parent.mkdir(parents=True, exist_ok=True)
        moment = when or datetime.now(tz=UTC)
        mode = "a"
        if target.exists():
            modified_year = datetime.fromtimestamp(target.stat().st_mtime, tz=UTC).year
            if modified_year < moment.year:
                mode = "w"  # stale file from a previous year -> overwrite
        self._handle = target.open(mode, encoding=self._encoding)
        self._current_path = target

    def write(self, data: str) -> int:
        """Write `data` to the file for the current day, rotating as needed."""
        self._ensure_handle()
        return self._handle.write(data)  # pyright: ignore[reportOptionalMemberAccess]

    def flush(self) -> None:
        """Flush the underlying file handle when open."""
        if self._handle is not None and not self._handle.closed:
            self._handle.flush()

    def close(self) -> None:
        """Close the underlying file handle."""
        if self._handle is not None and not self._handle.closed:
            self._handle.close()
        self.closed = True


@dataclass(frozen=True)
class OtlpConfig:  # noqa: D101
    service: str = DEFAULT_SERVICE_NAME
    http_exporter_endpoint: str | None = None
    http_exporter_headers: dict[str, str] | None = None
    metrics_file_exporter_url: str | None = None
    logs_file_exporter_url: str | None = None
    file_exporter_rotation: bool = False

    @staticmethod
    def resolve_from_env() -> "OtlpConfig":
        """Resolve OTLP configuration from environment variables.

        Always returns an `OtlpConfig`; unset variables fall back to defaults
        (`service` -> `"observability"`, exporters -> `None`, rotation -> off).
        """
        service = os.getenv(ENV_VAR_TGEDR_OBSERVABILITY_SERVICE) or DEFAULT_SERVICE_NAME
        headers = os.getenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS)

        headers_dict = None
        if headers:
            headers_dict = json.loads(headers)

        return OtlpConfig(
            service=service,
            http_exporter_endpoint=os.getenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT),
            http_exporter_headers=headers_dict,
            metrics_file_exporter_url=os.getenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_METRICS_FILE),
            logs_file_exporter_url=os.getenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_LOGS_FILE),
            file_exporter_rotation=_env_flag(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION),
        )


class ObservabilityError(Exception):
    """Exception raised for observability-related errors."""
