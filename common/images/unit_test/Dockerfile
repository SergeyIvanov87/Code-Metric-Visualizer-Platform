
FROM alpine:latest

WORKDIR tests

# install app dependencies
RUN apk add --no-cache python3 pytest dos2unix bash

COPY common/tests/*.py /tests/

# TODO temporary source of utils
RUN mkdir -p /tests/utils
COPY common/*.py /tests/utils/
COPY common/modules /tests/utils/modules

COPY common/images/unit_test*.py /tests
COPY common/images/API /

RUN dos2unix /tests/*
RUN dos2unix /tests/utils/*
RUN dos2unix /tests/utils/modules/*

ARG EXIT_ONCE_DONE=true
ENV EXIT_ONCE_DONE=$EXIT_ONCE_DONE

RUN dos2unix /init.sh

VOLUME ["/api", "/mnt"]

ENTRYPOINT ["/init.sh"]
