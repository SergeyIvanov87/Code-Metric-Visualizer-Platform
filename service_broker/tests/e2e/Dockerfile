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
RUN mkdir -p /tests
COPY service_broker/*.py /tests/

RUN dos2unix /tests/*

# TODO temporary solution due to issue #34 unresolved: add VOLUME /main_image_env
RUN mkdir /main_image_env
COPY cyclomatic_complexity/*.py /main_image_env/
VOLUME ["/api"]

ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]
