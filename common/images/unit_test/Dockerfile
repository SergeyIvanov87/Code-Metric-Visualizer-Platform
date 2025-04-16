
FROM alpine:latest

WORKDIR tests

ARG PYTEST_FILTER=
ENV PYTEST_FILTER=$PYTEST_FILTER

# install app dependencies
RUN apk add --no-cache coreutils python3 pytest dos2unix bash inotify-tools gdb python3-dbg

COPY common/tests/*.py /tests/

# TODO temporary source of utils
RUN mkdir -p /tests/utils
COPY common/*.py /tests/utils/
COPY common/modules /tests/utils/modules


COPY common/images/unit_test/API /API/
COPY common/images/unit_test/init.sh /

RUN dos2unix /tests/utils/*
RUN dos2unix /tests/utils/modules/*


ARG EXIT_ONCE_DONE=true
ENV EXIT_ONCE_DONE=$EXIT_ONCE_DONE

RUN dos2unix /init.sh

COPY common/images/unit_test/*.py /tests
RUN dos2unix /tests/*

ENTRYPOINT ["/init.sh", "/tests", "/api"]
