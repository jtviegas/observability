"""Common configuration models for observability integrations."""

from dataclasses import dataclass

LOCAL_METRICS_URL: str = "http://localhost:4318/v1/metrics"


@dataclass(frozen=True)
class OtlpConfig:  # noqa: D101
    endpoint: str
    headers: dict[str, str] | None = None


class ObservabilityError(Exception):
    """Exception raised for observability-related errors."""
