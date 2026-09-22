FROM python:3.12-slim

RUN python3 -m pip install --no-cache-dir \
    xds-protos==1.83.1 \
    confluent-kafka==2.11.1
RUN python3 -m pip check && python3 -c \
    "from confluent_kafka import Producer; from envoy.data.tap.v3 import wrapper_pb2; from google.protobuf import json_format"
RUN mkdir -p /logs /package
VOLUME ["/logs"]

COPY common/images/streaming_test_aggregator/tap_subscriber/bootstrap.sh /etc/bootstrap.sh
COPY common/images/streaming_test_aggregator/tap_subscriber/lifecycle_watchdog.sh /package/lifecycle_watchdog.sh
COPY common/images/streaming_test_aggregator/tap_subscriber/tap_subscriber.py /package/tap_subscriber.py
COPY common/images/streaming_test_aggregator/tap_subscriber/publish_capture_failure.py /package/publish_capture_failure.py
COPY common/images/streaming_test_aggregator/tap_subscriber/decode_envoy_tap.py /package/decode_envoy_tap.py
COPY common/images/streaming_test_aggregator/tap_subscriber/aggregate_connection_logs.py /package/aggregate_connection_logs.py
RUN chmod +x \
    /etc/bootstrap.sh \
    /package/lifecycle_watchdog.sh \
    /package/tap_subscriber.py \
    /package/publish_capture_failure.py \
    /package/decode_envoy_tap.py \
    /package/aggregate_connection_logs.py

ARG ENVOY_ADMIN_HOST=envoy
ARG ENVOY_ADMIN_PORT=9901
ARG MAX_BUFFERED_RX_BYTES=4294967295
ARG WAIT_FOR_NEXT_TAP_BEFORE_FINISH_MSEC=15000
ARG WAIT_FOR_FIRST_TAP_BEFORE_FINISH_MSEC=60000
ARG KAFKA_DELIVERY_TIMEOUT_SECONDS=120
ARG KAFKA_BOOTSTRAP_SERVERS=kafka:9092

ENV WAIT_FOR_NEXT_TAP_BEFORE_FINISH_MSEC=${WAIT_FOR_NEXT_TAP_BEFORE_FINISH_MSEC} \
    WAIT_FOR_FIRST_TAP_BEFORE_FINISH_MSEC=${WAIT_FOR_FIRST_TAP_BEFORE_FINISH_MSEC} \
    MAX_BUFFERED_RX_BYTES=${MAX_BUFFERED_RX_BYTES} \
    RETAIN_RAW_TAPS=false \
    ENVOY_ADMIN_HOST=${ENVOY_ADMIN_HOST} \
    ENVOY_ADMIN_PORT=${ENVOY_ADMIN_PORT} \
    ENVOY_TAP_CONFIG_ID=test_aggregator \
    KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS} \
    KAFKA_DELIVERY_TIMEOUT_SECONDS=${KAFKA_DELIVERY_TIMEOUT_SECONDS} \
    KAFKA_TOPIC=test-capture-events \
    CAPTURE_ID=functional-test

ENTRYPOINT ["/etc/bootstrap.sh"]

HEALTHCHECK --interval=2s --timeout=1s --retries=30 CMD test -f /logs/subscriber/status/subscriber_ready || exit 1
