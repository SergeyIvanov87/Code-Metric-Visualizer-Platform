FROM alpine:latest

WORKDIR tests

# install app dependencies
RUN apk add --no-cache python3 pytest dos2unix bash

COPY service_broker/API API

COPY common/tests/settings.py /tests/
COPY common/tests/utils.py /tests/

COPY service_broker/tests/e2e/*.py /tests/
COPY service_broker/tests/e2e/*.sh /tests/
#COPY service_broker/tests/e2e/data /tests/data

# TODO temporary source of utils
RUN mkdir -p /tests/utils
COPY service_broker/*.py /tests/

RUN dos2unix /tests/*

COPY common/*.py /tests/utils/
COPY common/modules /tests/utils/modules

RUN dos2unix /tests/*
RUN dos2unix /tests/utils/*
RUN dos2unix /tests/utils/modules/*

VOLUME ["/api"]

ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]
