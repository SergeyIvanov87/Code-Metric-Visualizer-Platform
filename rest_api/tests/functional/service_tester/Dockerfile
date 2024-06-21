FROM test_pseudo_fs:latest

# install app dependencies
RUN apk add --no-cache py3-requests curl

COPY rest_api/API /API

COPY rest_api/tests/functional/service_tester/*.py /tests/
COPY rest_api/tests/functional/service_tester/*.sh /tests/
COPY rest_api/tests/functional/data /tests/data

# TODO temporary source of utils
COPY rest_api/*.py /tests/

RUN dos2unix /tests/*
RUN dos2unix /tests/utils/*
RUN dos2unix /tests/utils/modules/*

VOLUME ["/api"]

ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]
