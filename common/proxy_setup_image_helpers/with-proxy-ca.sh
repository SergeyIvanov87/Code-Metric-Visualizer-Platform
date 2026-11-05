#!/bin/sh
# Optional trust for one command; compatible with Bash and Alpine's /bin/sh.
set -eu
if [ "$#" -eq 0 ]; then
    echo "Usage: with-proxy-ca.sh command [arguments...]" >&2
    exit 2
fi
extra_ca="${PROXY_CA_PATH:-/run/secrets/proxy_ca}"
system_ca="${SYSTEM_CA_FILE:-/etc/ssl/certs/ca-certificates.crt}"
if [ ! -s "$extra_ca" ]; then
    exec "$@"
fi
if [ ! -r "$extra_ca" ] || [ ! -r "$system_ca" ]; then
    echo "Cannot read the additional or system CA bundle" >&2
    exit 1
fi
bundle="$(mktemp)"
trap 'rm -f "$bundle"' EXIT
cat "$system_ca" > "$bundle"
printf '\n' >> "$bundle"
cat "$extra_ca" >> "$bundle"
export SSL_CERT_FILE="$bundle"
export REQUESTS_CA_BUNDLE="$bundle"
export PIP_CERT="$bundle"
export CURL_CA_BUNDLE="$bundle"

# Keep the wrapper alive for cleanup, and forward container shutdown signals.
child=""
terminate() {
    if [ -n "$child" ]; then
        kill -"$2" "$child" 2>/dev/null || true
        wait "$child" || true
    fi
    exit "$1"
}
trap 'terminate 130 INT' INT
trap 'terminate 143 TERM' TERM
# Save stdin before the shell substitutes /dev/null for a background job.
exec 3<&0
"$@" <&3 3<&- &
child=$!
exec 3<&-
if wait "$child"; then
    status=0
else
    status=$?
fi
exit "$status"
