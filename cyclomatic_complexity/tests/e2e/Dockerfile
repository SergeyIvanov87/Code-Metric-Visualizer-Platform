FROM alpine:latest

WORKDIR tests

# install app dependencies
RUN apk add --no-cache python3 pytest dos2unix bash

COPY cyclomatic_complexity/API /API

COPY common/tests/*.py /tests/
COPY cyclomatic_complexity/tests/e2e/*.py /tests/
COPY cyclomatic_complexity/tests/e2e/*.sh /tests/

# TODO think about sending those via ssh
COPY cyclomatic_complexity/tests/e2e/data /mnt/

# TODO temporary source of utils
RUN mkdir -p /tests/utils
COPY common/*.py /tests/utils/
COPY common/modules /tests/utils/modules

RUN dos2unix /tests/*
RUN dos2unix /tests/utils/*
RUN dos2unix /tests/utils/modules/*

VOLUME ["/api", "/mnt"]
ENTRYPOINT ["/tests/init.sh", "/tests", "/mnt", "/api"]
