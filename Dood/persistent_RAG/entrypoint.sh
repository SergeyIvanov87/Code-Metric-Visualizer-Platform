#!/bin/sh
set -eu
export DOCKER_CONFIG=/tmp/docker
mkdir -p "$DOCKER_CONFIG"
# Only this endpoint is available to the controller; no raw socket is mounted.
compose() { docker compose -f /opt/persistent-rag/stack.yaml "$@"; }
cleanup() {
    trap - TERM INT EXIT
    compose down --timeout 30 || true
}
trap 'exit 0' TERM INT
trap cleanup EXIT
attempt=0
until docker version >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    [ "$attempt" -lt 60 ] || { echo 'Socket proxy unavailable' >&2; exit 1; }
    sleep 1 & wait $!
done
docker load -i /opt/persistent-rag/images.tar
compose up -d --wait --wait-timeout 600 &
wait $!
echo 'Persistent RAG is ready; filesystem API volume:' "$FS_API_VOLUME"
while :; do
    sleep 15 & wait $!
    # Reconcile missing/stopped siblings after host-daemon restarts.
    compose up -d --wait --wait-timeout 600 &
    wait $!
done
