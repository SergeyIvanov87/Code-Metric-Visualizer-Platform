#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# Some Compose versions return success on wait timeout during restart loops.
# Independently verify actual health before allowing any API queries.
docker compose -f "$HERE/compose-test-functional.yml" up -d --no-build --wait --wait-timeout 900 rag
check_health() {
    compose_file=$1
    service=$2
    container=$(docker compose -f "$compose_file" ps --all --quiet "$service")
    if [ -z "$container" ]; then
        echo "Required service $service has no container" >&2
        return 1
    fi
    status=$(docker inspect --format '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{else}}missing-healthcheck{{end}}' "$container")
    if [ "$status" != running/healthy ]; then
        echo "Required service $service is $status; refusing to run functional tests" >&2
        docker inspect --format '{{json .State}}' "$container" >&2
        return 1
    fi
}
check_health "$HERE/compose-test-functional.yml" rag
for service in rag-db docs-dispatcher ai-agent; do
    check_health "$HERE/../../stack.yaml" "$service"
done
