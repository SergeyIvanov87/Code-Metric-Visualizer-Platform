#!/bin/sh
# Source this file, then call configure_proxy_ca [optional PEM file].
# Missing and empty files leave system trust and caller settings unchanged.
configure_proxy_ca() {
    local ca_file="${1:-/run/secrets/proxy_ca}"
    [ -s "$ca_file" ] || return 0
    REST_PROXY_CA_BUNDLE=$(mktemp) || return 1
    if ! { cat /etc/ssl/certs/ca-certificates.crt; printf '\n'; cat "$ca_file"; } > "$REST_PROXY_CA_BUNDLE"; then
        rm -f "$REST_PROXY_CA_BUNDLE"
        return 1
    fi
    export SSL_CERT_FILE="$REST_PROXY_CA_BUNDLE"
    export REQUESTS_CA_BUNDLE="$REST_PROXY_CA_BUNDLE"
    export PIP_CERT="$REST_PROXY_CA_BUNDLE"
    export CURL_CA_BUNDLE="$REST_PROXY_CA_BUNDLE"
}
