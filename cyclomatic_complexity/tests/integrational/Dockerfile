FROM test_pseudo_fs:latest

COPY cyclomatic_complexity/API /API
COPY common/API /API/deps
COPY cyclomatic_complexity/API /API/deps/cyclomatic_complexity

COPY cyclomatic_complexity/tests/integrational/*.py /tests/
COPY cyclomatic_complexity/tests/integrational/*.sh /tests/

RUN dos2unix /tests/*

ARG MICROSERVICE_NAME=cc-integrational-tester
ENV MICROSERVICE_NAME=$MICROSERVICE_NAME

VOLUME ["/api", "/mnt"]
ENTRYPOINT ["/tests/init.sh", "/tests", "/mnt", "/api"]
