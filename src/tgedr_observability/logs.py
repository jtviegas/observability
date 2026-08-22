"""OpenTelemetry logging setup and singleton manager for application logs."""

import logging
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import (
    BatchLogRecordProcessor,
    ConsoleLogRecordExporter,
)  # ConsoleLogExporter on versions earlier than 1.39.0
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from tgedr_pycommons.utils.singleton import SingletonMeta
from tgedr_observability.commons import OtlpConfig


class Logs(metaclass=SingletonMeta):
    """Singleton manager for configuring OpenTelemetry logging."""

    @staticmethod
    def instance(otlp_config: OtlpConfig | None = None) -> "Logs | None":
        """Get the singleton instance of the Logs manager."""
        instance = Logs()  # pyright: ignore[reportReturnType]
        if instance._logger_provider is None:  # pyright: ignore[reportAttributeAccessIssue]
            config = otlp_config or OtlpConfig.resolve_from_env()
            if config is not None:
                instance._Logs__bootstrap(config)  # pyright: ignore[reportAttributeAccessIssue]
            else:
                return None
        return instance  # pyright: ignore[reportReturnType]

    def __init__(self) -> None:
        """Initialize the singleton logs manager state."""
        self._logger_provider: LoggerProvider | None = None
        self._handler: LoggingHandler | None = None

    def __bootstrap(self, otlp_config: OtlpConfig) -> None:
        """Initialize the logging provider and configure log exporting."""
        if self._logger_provider is None:
            resource = Resource.create(attributes={SERVICE_NAME: otlp_config.service})  # pyright: ignore[reportOptionalMemberAccess]
            provider = LoggerProvider(resource=resource)
            provider.add_log_record_processor(BatchLogRecordProcessor(ConsoleLogRecordExporter()))

            if otlp_config.endpoint is not None:
                otlp_exporter = OTLPLogExporter(
                    endpoint=otlp_config.endpoint,
                    headers=otlp_config.headers,
                )
                provider.add_log_record_processor(BatchLogRecordProcessor(otlp_exporter))

            set_logger_provider(provider)

            handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
            logging.basicConfig(handlers=[handler], level=logging.INFO, force=True)
            self._handler = handler
            self._logger_provider = provider

    def force_flush(self, timeout_millis: int = 10_000) -> bool:
        """Force export of pending logs from all configured processors."""
        if self._logger_provider is None:
            return False
        return self._logger_provider.force_flush(timeout_millis=timeout_millis)

    def shutdown(self) -> None:
        """Shut down log processing and detach the OpenTelemetry handler."""
        if self._logger_provider is None:
            return

        self._logger_provider.shutdown()
        self._logger_provider = None

        if self._handler is not None:
            root_logger = logging.getLogger()
            root_logger.handlers = [
                existing_handler for existing_handler in root_logger.handlers if existing_handler is not self._handler
            ]
            self._handler.close()
            self._handler = None

    @staticmethod
    def app_shutdown() -> None:
        """Application shutdown hook for logs.

        add shutdownhook to flush and shutdown the logs provider on application exit.
        ````
        import atexit
        atexit.register(Logs.app_shutdown)
            ````
        """
        instance = Logs.instance()
        if instance is None:
            return
        instance.force_flush()
        instance.shutdown()


Logs.instance()
