FROM python:3.12-slim

RUN python3 -m pip install --no-cache-dir xds-protos==1.83.1
RUN mkdir -p /logs /package
VOLUME ["/logs"]

COPY common/images/test_aggregator_subscriber_image/bootstrap.sh /etc/bootstrap.sh
COPY common/images/test_aggregator_subscriber_image/streaming_admin_tap.py /package/streaming_admin_tap.py
COPY common/images/test_aggregator_subscriber_image/decode_envoy_tap.py /package/decode_envoy_tap.py
COPY common/images/test_aggregator_subscriber_image/log_aggregator.py /package/log_aggregator.py
COPY common/images/test_aggregator_subscriber_image/log_watcher_service.sh /package/log_watcher_service.sh
RUN chmod +x /etc/bootstrap.sh /package/*.sh /package/*.py

ENV WAIT_MSEC_UNTIL_FINISH=15000 \
    MAX_WAIT_MSEC_UNTIL_FINISH=900000 \
    MAX_BUFFERED_RX_BYTES=16777216 \
    ENVOY_ADMIN_HOST=envoy \
    ENVOY_ADMIN_PORT=9901 \
    ENVOY_TAP_CONFIG_ID=test_aggregator

ENTRYPOINT ["/etc/bootstrap.sh"]

HEALTHCHECK --interval=2s --timeout=1s --retries=30 CMD test -f /logs/aggregator/subscriber_ready || exit 1
