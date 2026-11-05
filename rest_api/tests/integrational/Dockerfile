# syntax=docker/dockerfile:1

FROM test_pseudo_fs

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

COPY rest_api/*.py /tests/
COPY rest_api/tests/*.py /tests/
COPY rest_api/tests/integrational/*.sh /tests/
COPY rest_api/tests/integrational/*.py /tests/

# copy API schemas
COPY cyclomatic_complexity/API/*.json /tests/collected_API/
COPY rrd_analytic/API/*.json /tests/collected_API/

RUN dos2unix /tests/*

VOLUME ["/api"]

ENTRYPOINT ["/tests/init.sh", "/tests", "/api"]
