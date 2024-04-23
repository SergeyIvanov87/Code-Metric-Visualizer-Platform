FROM alpine:latest

WORKDIR tests

# install app dependencies
RUN apk add --no-cache python3 dos2unix bash

COPY rest_api/API /API
COPY rest_api/tests/e2e/api_initializer/*.sh /tests/
COPY rest_api/tests/e2e/api_initializer/*.py /tests/
COPY rest_api/tests/e2e/data /tests/data

RUN mkdir -p /tests/utils
COPY common/*.py /tests/utils/
COPY common/modules /tests/utils/modules

RUN dos2unix /tests/*
RUN dos2unix /tests/utils/*
RUN dos2unix /tests/utils/modules/*

VOLUME ["/api"]

ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]
