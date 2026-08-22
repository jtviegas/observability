"""Common configuration models for observability integrations."""

from dataclasses import dataclass
import os
import json

LOCAL_METRICS_URL: str = "http://localhost:4318/v1/metrics"
ENV_VAR_TGEDR_OBSERVABILITY_SERVICE: str = "TGEDR_OBSERVABILITY_SERVICE"
ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT: str = "TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT"
ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS: str = "TGEDR_OBSERVABILITY_EXPORTER_HEADERS"


@dataclass(frozen=True)
class OtlpConfig:  # noqa: D101
    service: str
    endpoint: str | None = None
    headers: dict[str, str] | None = None

    @staticmethod
    def resolve_from_env() -> "OtlpConfig | None":
        """Resolve OTLP configuration from environment variables."""
        result = None
        service = os.getenv(ENV_VAR_TGEDR_OBSERVABILITY_SERVICE)
        if service is not None:
            endpoint = os.getenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT)
            headers = os.getenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS)

            headers_dict = None
            if headers:
                headers_dict = json.loads(headers)
            if endpoint:
                result = OtlpConfig(service=service, endpoint=endpoint, headers=headers_dict)
        return result


class ObservabilityError(Exception):
    """Exception raised for observability-related errors."""
