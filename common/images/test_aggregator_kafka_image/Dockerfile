FROM python:3.12-slim
RUN python3 -m pip install --no-cache-dir confluent-kafka==2.11.1 pyinotify==0.9.6
RUN mkdir -p /logs /package
VOLUME ["/logs"]
COPY common/images/test_aggregator_kafka_image/bootstrap.sh /etc/bootstrap.sh
COPY common/images/test_aggregator_kafka_image/kafka_test_aggregator.py /package/kafka_test_aggregator.py
COPY common/images/test_aggregator_kafka_image/log_aggregator.py /package/log_aggregator.py
COPY common/images/test_aggregator_kafka_image/log_watcher_service.sh /package/log_watcher_service.sh
RUN chmod +x /etc/bootstrap.sh /package/*.py /package/*.sh
ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092 KAFKA_TOPIC=test-capture-events \
    KAFKA_CONSUMER_GROUP=test-aggregator CAPTURE_ID=functional-test MAX_WAIT_SECONDS=900
HEALTHCHECK --interval=2s --timeout=1s --retries=30 CMD test -f /logs/aggregator/consumer_ready || exit 1
ENTRYPOINT ["/etc/bootstrap.sh"]
