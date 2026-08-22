"""Unit tests for commons module configuration helpers."""

from tgedr_observability.commons import (
    ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT,
    ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS,
    ENV_VAR_TGEDR_OBSERVABILITY_SERVICE,
    OtlpConfig,
)


def test_resolve_from_env_without_endpoint_returns_none(monkeypatch) -> None:
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_SERVICE, "test-service")
    monkeypatch.delenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT, raising=False)
    monkeypatch.delenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS, raising=False)

    assert OtlpConfig.resolve_from_env() is None


def test_resolve_from_env_without_service_returns_none(monkeypatch) -> None:
    monkeypatch.delenv(ENV_VAR_TGEDR_OBSERVABILITY_SERVICE, raising=False)
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT, "http://localhost:4318/v1/metrics")
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS, '{"Authorization": "Bearer token"}')

    assert OtlpConfig.resolve_from_env() is None


def test_resolve_from_env_with_endpoint_and_headers(monkeypatch) -> None:
    endpoint = "http://localhost:4318/v1/metrics"
    headers_json = '{"Authorization": "Bearer token", "x-scope": "test"}'

    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_SERVICE, "test-service")
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_ENDPOINT, endpoint)
    monkeypatch.setenv(ENV_VAR_TGEDR_OBSERVABILITY_EXPORTER_HEADERS, headers_json)

    config = OtlpConfig.resolve_from_env()

    assert config is not None
    assert config.service == "test-service"
    assert config.endpoint == endpoint
    assert config.headers == {"Authorization": "Bearer token", "x-scope": "test"}
