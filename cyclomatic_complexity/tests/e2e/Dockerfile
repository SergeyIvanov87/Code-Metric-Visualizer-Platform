FROM alpine:latest

WORKDIR tests

# install app dependencies
RUN apk add --no-cache python3 pytest dos2unix bash

COPY cyclomatic_complexity/API /API

COPY common/tests/*.py /tests/
COPY cyclomatic_complexity/tests/e2e/*.py /tests/
COPY cyclomatic_complexity/tests/e2e/*.sh /tests/

# TODO temporary source of utils
RUN mkdir -p /tests/utils
COPY cyclomatic_complexity/*.py /tests/utils/

RUN dos2unix /tests/*

VOLUME ["/api", "/mnt"]
ENTRYPOINT ["/tests/init.sh", "/tests", "/mnt", "/api"]
