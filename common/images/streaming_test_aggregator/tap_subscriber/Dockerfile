FROM python:3.12-slim

RUN python3 -m pip install --no-cache-dir \
    xds-protos==1.83.1 \
    confluent-kafka==2.11.1
RUN python3 -m pip check && python3 -c \
    "from confluent_kafka import Producer; from envoy.data.tap.v3 import wrapper_pb2; from google.protobuf import json_format"
RUN mkdir -p /logs /package
VOLUME ["/logs"]

COPY common/images/streaming_test_aggregator/tap_subscriber/bootstrap.sh /etc/bootstrap.sh
COPY common/images/streaming_test_aggregator/tap_subscriber/tap_subscriber.py /package/tap_subscriber.py
COPY common/images/streaming_test_aggregator/tap_subscriber/publish_capture_failure.py /package/publish_capture_failure.py
COPY common/images/streaming_test_aggregator/tap_subscriber/decode_envoy_tap.py /package/decode_envoy_tap.py
RUN chmod +x \
    /etc/bootstrap.sh \
    /package/tap_subscriber.py \
    /package/publish_capture_failure.py \
    /package/decode_envoy_tap.py

ENV WAIT_MSEC_UNTIL_FINISH=15000 \
    WAIT_MSEC_BEFORE_START=60000 \
    MAX_WAIT_MSEC_UNTIL_FINISH=900000 \
    MAX_BUFFERED_RX_BYTES=16777216 \
    RETAIN_RAW_TAPS=false \
    ENVOY_ADMIN_HOST=envoy \
    ENVOY_ADMIN_PORT=9901 \
    ENVOY_TAP_CONFIG_ID=test_aggregator \
    KAFKA_BOOTSTRAP_SERVERS=kafka:9092 \
    KAFKA_STARTUP_TIMEOUT_SECONDS=120 \
    KAFKA_TOPIC=test-capture-events \
    CAPTURE_ID=functional-test

ENTRYPOINT ["/etc/bootstrap.sh"]

HEALTHCHECK --interval=2s --timeout=1s --retries=30 CMD test -f /logs/subscriber/status/subscriber_ready || exit 1
