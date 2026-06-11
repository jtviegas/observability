ARG OTEL_COLLECTOR_IMG_VERSION=0.153.0
FROM otel/opentelemetry-collector-contrib:${OTEL_COLLECTOR_IMG_VERSION}

COPY otel-collector-config.yaml /etc/otelcol-contrib/config.yaml
USER 10001
EXPOSE 4318
