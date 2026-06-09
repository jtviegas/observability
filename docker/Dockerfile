ARG OTEL_COLLECTOR_IMG_VERSION=0.153.0

FROM busybox AS prep
RUN mkdir -p /output

FROM otel/opentelemetry-collector-contrib:${OTEL_COLLECTOR_IMG_VERSION}

COPY --from=prep /output /output
COPY otel-collector-config.yaml /etc/otelcol-contrib/config.yaml

EXPOSE 4318
