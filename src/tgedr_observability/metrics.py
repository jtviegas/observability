"""Metrics manager and helpers for OpenTelemetry instrumentation."""

from pathlib import Path

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.metrics import Instrument
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from tgedr_pycommons.utils.singleton import SingletonMeta
from tgedr_observability.commons import ObservabilityError, OtlpConfig


class Metrics(metaclass=SingletonMeta):
    """Singleton manager for meter creation and metric recording."""

    @staticmethod
    def instance(otlp_config: OtlpConfig | None = None) -> "Metrics | None":
        """Get the singleton instance of the Metrics manager."""
        instance = Metrics()  # pyright: ignore[reportReturnType]
        if instance._meter_provider is None:  # pyright: ignore[reportAttributeAccessIssue]
            config = otlp_config or OtlpConfig.resolve_from_env()
            if config is not None:
                instance._Metrics__bootstrap(config)  # pyright: ignore[reportAttributeAccessIssue]
            else:
                return None
        return instance  # pyright: ignore[reportReturnType]

    def __init__(self) -> None:
        """Initialize the singleton metrics manager state."""
        self._meter_provider: MeterProvider | None = None
        self._meters: dict[str, metrics.Meter] = {}
        self._counters: dict[str, metrics.UpDownCounter] = {}
        self._gauges: dict[str, Instrument] = {}
        self._histograms: dict[str, metrics.Histogram] = {}
        self._log_file = None

    def __bootstrap(self, otlp_config: OtlpConfig) -> None:
        """Initialize the metrics provider and configure metric exporting."""
        if self._meter_provider is None:
            resource = Resource.create(attributes={SERVICE_NAME: otlp_config.service})  # pyright: ignore[reportOptionalMemberAccess]
            readers = []
            # Add the console metric exporter by default
            console_exporter = ConsoleMetricExporter()
            reader_console = PeriodicExportingMetricReader(console_exporter)
            readers.append(reader_console)

            # Add the file metric exporter if a file URL is specified
            if otlp_config.metrics_file_exporter_url is not None:
                Path(otlp_config.metrics_file_exporter_url).parent.mkdir(parents=True, exist_ok=True)
                Path(otlp_config.metrics_file_exporter_url).touch()
                self._log_file = open(otlp_config.metrics_file_exporter_url, "a", encoding="utf-8")  # noqa: PTH123, SIM115
                file_exporter = ConsoleMetricExporter(out=self._log_file)
                reader_file = PeriodicExportingMetricReader(file_exporter)
                readers.append(reader_file)

            # Add the HTTP metric exporter if an endpoint is specified
            if otlp_config.http_exporter_endpoint is not None:
                http_exporter = OTLPMetricExporter(
                    endpoint=otlp_config.http_exporter_endpoint,
                    headers=otlp_config.http_exporter_headers,
                )
                reader_http = PeriodicExportingMetricReader(http_exporter, export_interval_millis=5000)
                readers.append(reader_http)

            provider = MeterProvider(metric_readers=readers, resource=resource)
            metrics.set_meter_provider(provider)  # Set the global meter provider
            self._meter_provider = provider

    def _get_meter(self, name: str) -> metrics.Meter:
        toponomy: list[str] = name.split(".")
        if len(toponomy) < 2:
            error_message = "Metric name must have at least two parts separated by '.'"
            raise ObservabilityError(error_message)
        meter_name = ".".join(toponomy[:-1])

        if meter_name not in self._meters:
            self._meters[meter_name] = metrics.get_meter(meter_name)
        meter = self._meters[meter_name]
        return meter

    def _get_counter(self, name: str) -> metrics.UpDownCounter:
        if name not in self._counters:
            meter = self._get_meter(name)
            toponomy: list[str] = name.split(".")
            counter_name = toponomy[-1]
            self._counters[name] = meter.create_up_down_counter(
                counter_name, unit="1", description=f"Counter metric for {name}"
            )
        return self._counters[name]

    def _get_gauge(self, name: str) -> Instrument:
        if name not in self._gauges:
            meter = self._get_meter(name)
            toponomy: list[str] = name.split(".")
            gauge_name = toponomy[-1]
            gauge_type = "s" if gauge_name[-2:] == "_s" else "1"
            self._gauges[name] = meter.create_gauge(gauge_name, unit=gauge_type, description=f"Gauge metric for {name}")
        return self._gauges[name]

    def _get_histogram(self, name: str) -> metrics.Histogram:
        if name not in self._histograms:
            meter = self._get_meter(name)
            toponomy: list[str] = name.split(".")
            histogram_name = toponomy[-1]
            histogram_type = "s" if histogram_name[-2:] == "_s" else "1"
            self._histograms[name] = meter.create_histogram(
                histogram_name, unit=histogram_type, description=f"Histogram metric for {name}"
            )
        return self._histograms[name]

    def add_to_counter(self, name: str, value: int, attributes: dict[str, str] | None = None) -> None:
        """Add a value to the named counter metric."""
        counter = self._get_counter(name)
        counter.add(value, attributes=attributes)

    def add_to_gauge(self, name: str, value: float, attributes: dict[str, str] | None = None) -> None:
        """Add a value to the named gauge metric."""
        gauge = self._get_gauge(name)
        gauge.set(value, attributes=attributes)  # pyright: ignore[reportAttributeAccessIssue]

    def add_to_histogram(self, name: str, value: float, attributes: dict[str, str] | None = None) -> None:
        """Add a value to the named histogram metric."""
        histogram = self._get_histogram(name)
        histogram.record(value, attributes=attributes)

    def force_flush(self, timeout_millis: int = 10_000) -> bool:
        """Force export of pending metrics from all configured readers."""
        if self._meter_provider is None:
            error_message = "Metrics provider is not initialized. Call init() first."
            raise ObservabilityError(error_message)
        return self._meter_provider.force_flush(timeout_millis=timeout_millis)

    def shutdown(self) -> None:
        """Shut down the metrics pipeline and clear cached instruments."""
        if self._meter_provider is None:
            return

        self._meter_provider.shutdown()
        self._meter_provider = None
        self._meters.clear()
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()

        if self._log_file is not None and not self._log_file.closed:
            self._log_file.close()
            self._log_file = None

    @staticmethod
    def app_shutdown() -> None:
        """Application shutdown hook for metrics.

        add shutdownhook to flush and shutdown the metrics provider on application exit.
        ````
        import atexit
        atexit.register(Metrics.app_shutdown)
        ````
        """
        instance = Metrics.instance()
        if instance is None:
            return
        instance.force_flush()
        instance.shutdown()
