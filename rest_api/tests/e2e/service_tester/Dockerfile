FROM alpine:latest

WORKDIR tests

# install app dependencies
RUN apk add --no-cache python3 py3-requests pytest curl dos2unix bash

COPY rest_api/API /API

COPY common/tests/*.py /tests/
COPY rest_api/tests/e2e/service_tester/*.py /tests/
COPY rest_api/tests/e2e/service_tester/*.sh /tests/
COPY rest_api/tests/e2e/data /tests/data

# TODO temporary source of utils
RUN mkdir -p /tests/utils
COPY rest_api/*.py /tests/

RUN dos2unix /tests/*

COPY common/*.py /tests/utils/
COPY common/modules /tests/utils/modules

RUN dos2unix /tests/*
RUN dos2unix /tests/utils/*
RUN dos2unix /tests/utils/modules/*

VOLUME ["/api"]

ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]
