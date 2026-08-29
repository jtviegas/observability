"""Common configuration models for observability integrations."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION_DAYS: str = "TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION_DAYS"


def dated_path(base_path: str | Path, when: datetime | None = None) -> Path:
    """Build a YYYYMMDD dated variant of `base_path`.

    `/var/log/app/metrics.log` -> `/var/log/app/metrics.20260829.log` on Aug 29, 2026.
    The date is formatted as YYYYMMDD for easy sorting and retention-based cleanup.
    """
    moment = when or datetime.now(tz=UTC)
    date_str = moment.strftime("%Y%m%d")
    path = Path(base_path)
    return path.with_name(f"{path.stem}.{date_str}{path.suffix}")


class DayOfYearRotatingFile:
    """Write-through text file that rotates daily by date (YYYYMMDD format).

    Behaves like a writable text file for exporters that hold an `out` stream.
    On each write it targets `base_path` rewritten with the current date (YYYYMMDD).
    Optionally cleans up old files based on retention days when a new day's file is created.
    """

    def __init__(self, base_path: str | Path, encoding: str = "utf-8", retention_days: int | None = None) -> None:
        """Create the rotating file for the given base path.

        Args:
            base_path: The base file path (e.g., /var/log/app/metrics.log)
            encoding: File encoding (default: utf-8)
            retention_days: If set, delete files older than this many days when rotating
        """
        self._base_path = Path(base_path)
        self._encoding = encoding
        self._retention_days = retention_days
        self._current_path: Path | None = None
        self._handle = None
        self.closed = False

    def _cleanup_old_files(self) -> None:
        """Delete files older than retention_days based on filename date (YYYYMMDD format)."""
        if self._retention_days is None:
            return

        now = datetime.now(tz=UTC)
        cutoff_date = (now - timedelta(days=self._retention_days)).strftime("%Y%m%d")

        parent = self._base_path.parent
        stem = self._base_path.stem
        suffix = self._base_path.suffix

        for file_path in parent.glob(f"{stem}.????????{suffix}"):
            # Extract date from filename (e.g., "metrics.20260829.log" -> "20260829")
            parts = file_path.stem.split(".")
            if len(parts) >= 2 and parts[-1].isdigit() and len(parts[-1]) == 8:
                file_date = parts[-1]
                if file_date < cutoff_date:
                    file_path.unlink()

    def _ensure_handle(self, when: datetime | None = None) -> None:
        target = dated_path(self._base_path, when)
        if self._handle is not None and self._current_path == target and not self._handle.closed:
            return

        if self._handle is not None and not self._handle.closed:
            self._handle.close()

        target.parent.mkdir(parents=True, exist_ok=True)

        # Cleanup old files if this is a new day's file
        if self._current_path != target:
            self._cleanup_old_files()

        self._handle = target.open("a", encoding=self._encoding)
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
    file_rotation_days: int | None = None

    @staticmethod
    def resolve_from_env() -> "OtlpConfig":
        """Resolve OTLP configuration from environment variables.

        Always returns an `OtlpConfig`; unset variables fall back to defaults
        (`service` -> `"observability"`, exporters -> `None`, file_rotation_days -> `None`).

        file_rotation_days: If set to a positive integer, enables daily file rotation
        with automatic cleanup of files older than the specified number of days.
        """
        service = os.getenv(ENV_VAR_TGEDR_OBSERVABILITY_SERVICE) or DEFAULT_SERVICE_NAME
        headers = os.getenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS)

        headers_dict = None
        if headers:
            headers_dict = json.loads(headers)

        # Parse file rotation days (None if not set, or positive int if set)
        file_rotation_days_str = os.getenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_FILE_ROTATION_DAYS)
        file_rotation_days = None
        if file_rotation_days_str is not None:
            try:
                parsed_days = int(file_rotation_days_str)
                if parsed_days > 0:
                    file_rotation_days = parsed_days
            except ValueError:
                file_rotation_days = None

        return OtlpConfig(
            service=service,
            http_exporter_endpoint=os.getenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT),
            http_exporter_headers=headers_dict,
            metrics_file_exporter_url=os.getenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_METRICS_FILE),
            logs_file_exporter_url=os.getenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_LOGS_FILE),
            file_rotation_days=file_rotation_days,
        )


class ObservabilityError(Exception):
    """Exception raised for observability-related errors."""
