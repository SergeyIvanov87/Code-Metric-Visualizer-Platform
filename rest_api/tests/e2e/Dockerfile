FROM alpine:latest

WORKDIR tests

# install app dependencies
RUN apk add --no-cache python3 py3-requests pytest dos2unix bash

COPY rest_api/API /API

COPY common/tests/*.py /tests/
COPY rest_api/tests/e2e/*.py /tests/
COPY rest_api/tests/e2e/*.sh /tests/
COPY rest_api/tests/e2e/data /tests/data

# TODO temporary source of utils
RUN mkdir -p /tests
COPY rest_api/*.py /tests/

RUN dos2unix /tests/*

# TODO temporary solution due to issue #34 unresolved: add VOLUME /main_image_env
RUN mkdir /main_image_env
RUN dos2unix /tests/*
COPY cyclomatic_complexity/*.py /main_image_env/
VOLUME ["/api", "/main_image_env"]

ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]
