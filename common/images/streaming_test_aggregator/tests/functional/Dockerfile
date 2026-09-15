FROM python:3.12-alpine
RUN pip install --no-cache-dir pytest
COPY common/images/streaming_test_aggregator/tests/functional /tests
RUN chmod +x /tests/init.sh
ENTRYPOINT ["/tests/init.sh"]
