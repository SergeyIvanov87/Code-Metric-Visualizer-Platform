
FROM alpine:latest

WORKDIR tests

ARG PYTEST_FILTER=
ENV PYTEST_FILTER=$PYTEST_FILTER

# install app dependencies
RUN apk add --no-cache coreutils python3 pytest dos2unix bash inotify-tools shunit2

# prepare packages for debugging
RUN apk add --no-cache cython gdb python3-dbg

COPY common/tests/*.py /tests/

# TODO temporary source of utils
RUN <<EOF
mkdir -p /tests/utils
mkdir -p /tests/bash
EOF

COPY common/*.py /tests/utils/
COPY common/modules /tests/utils/modules


COPY common/images/unit_test/API /API/
COPY common/images/unit_test/init.sh /
COPY common/shell_utils /tests/shell_utils

RUN <<EOF
dos2unix /tests/shell_utils/*
dos2unix /tests/utils/*
dos2unix /tests/utils/modules/*
EOF

ARG EXIT_ONCE_DONE=true
ENV EXIT_ONCE_DONE=$EXIT_ONCE_DONE

RUN dos2unix /init.sh

COPY common/images/unit_test/*.py /tests
COPY common/images/unit_test/bash/*.sh /tests/bash

RUN <<EOF
dos2unix /tests/*
dos2unix /tests/bash/*
EOF

ENTRYPOINT ["/init.sh", "/tests", "/api"]
