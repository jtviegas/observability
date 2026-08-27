"""Common configuration models for observability integrations."""

from dataclasses import dataclass
import os
import json

LOCAL_METRICS_URL: str = "http://localhost:4318/v1/metrics"
DEFAULT_SERVICE_NAME: str = "observability"
ENV_VAR_TGEDR_OBSERVABILITY_SERVICE: str = "TGEDR_OBSERVABILITY_SERVICE"
ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT: str = "TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT"
ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS: str = "TGEDR_OBSERVABILITY_EXPORTER_HEADERS"
ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_METRICS_FILE: str = "TGEDR_OBSERVABILITY_EXPORTER_METRICS_FILE"
ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_LOGS_FILE: str = "TGEDR_OBSERVABILITY_EXPORTER_LOGS_FILE"


@dataclass(frozen=True)
class OtlpConfig:  # noqa: D101
    service: str = DEFAULT_SERVICE_NAME
    http_exporter_endpoint: str | None = None
    http_exporter_headers: dict[str, str] | None = None
    metrics_file_exporter_url: str | None = None
    logs_file_exporter_url: str | None = None

    @staticmethod
    def resolve_from_env() -> "OtlpConfig":
        """Resolve OTLP configuration from environment variables.

        Always returns an `OtlpConfig`; unset variables fall back to defaults
        (`service` -> `"observability"`, exporters -> `None`).
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
        )


class ObservabilityError(Exception):
    """Exception raised for observability-related errors."""
