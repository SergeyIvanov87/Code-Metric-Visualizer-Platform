# syntax=docker/dockerfile:1

FROM alpine:3.20.6

WORKDIR tests

# install app dependencies
# Optional extra trust is used only during this RUN, never stored in a layer.
RUN --mount=type=secret,id=proxy_ca,mode=0444 \
    set -eu; \
    ca_bundle="$(mktemp)"; \
    trap 'rm -f "$ca_bundle"' EXIT; \
    cat /etc/ssl/certs/ca-certificates.crt > "$ca_bundle"; \
    if [ -s /run/secrets/proxy_ca ]; then \
        printf '\n' >> "$ca_bundle"; \
        cat /run/secrets/proxy_ca >> "$ca_bundle"; \
    fi; \
    SSL_CERT_FILE="$ca_bundle" apk add --no-cache coreutils python3 pytest dos2unix inotify-tools bash

COPY common/tests/*.py /tests/

# TODO temporary source of utils
RUN mkdir -p /tests/utils
COPY common/*.py /tests/utils/
COPY common/modules /tests/utils/modules
COPY common/shell_utils /tests/utils/shell_utils

RUN dos2unix /tests/*
RUN dos2unix /tests/utils/*
RUN dos2unix /tests/utils/modules/*
RUN dos2unix /tests/utils/shell_utils/*

ARG EXIT_ONCE_DONE=true
ENV EXIT_ONCE_DONE=$EXIT_ONCE_DONE

COPY common/images/test_pseudo_fs/init.sh /init.sh
RUN dos2unix /init.sh

VOLUME ["/api", "/mnt"]

ENTRYPOINT ["/init.sh"]
