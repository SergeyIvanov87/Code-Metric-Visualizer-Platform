# syntax=docker/dockerfile:1

FROM test_pseudo_fs

ARG UID=9202
ENV UID=$UID
ARG GID=23456
ENV GID=$GID

ARG USER=rest-api-functional-service-tester
ENV USER=$USER
ENV GROUPNAME=pmccabe

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
    SSL_CERT_FILE="$ca_bundle" apk add --no-cache py3-requests curl

COPY rest_api/API /API

COPY rest_api/tests/*.py /tests/
COPY rest_api/proxy_ca.sh /tests/utils/proxy_ca.sh
COPY rest_api/tests/functional/service_tester/*.py /tests/
COPY rest_api/tests/functional/service_tester/*.sh /tests/
COPY rest_api/tests/functional/data /tests/data

# TODO temporary source of utils
COPY rest_api/*.py /tests/

RUN dos2unix /tests/*
RUN dos2unix /tests/utils/*
RUN dos2unix /tests/utils/modules/*

VOLUME ["/api"]

RUN addgroup \
    --gid "$GID" \
    "$GROUPNAME" \
&&  adduser \
    --disabled-password \
    --gecos "" \
    --home "$(pwd)" \
    -u $UID \
    --ingroup "$GROUPNAME" \
    --no-create-home \
    $USER

RUN mkdir -p -m 777 /api && chown -R ${USER}:${GROUPNAME} /api
RUN chown -R ${USER}:${GROUPNAME} /API && chown -R ${USER}:${GROUPNAME} /tests

USER ${USER}
ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]
