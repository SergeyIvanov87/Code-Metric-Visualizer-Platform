FROM test_pseudo_fs:latest

COPY service_broker/API API
COPY service_broker/tests/functional/*.py /tests/
COPY service_broker/tests/functional/*.sh /tests/
COPY service_broker/*.py /tests/

RUN dos2unix /tests/*

VOLUME ["/api"]

ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]

