#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$HERE/../.." && pwd)
compose() { docker compose -f "$HERE/compose.yaml" "$@"; }
build() {
    [ -d "$ROOT/ai_agents_framework" ] || {
        echo 'Build requires this folder at Dood/persistent_RAG in the source repository.' >&2
        exit 1
    }
    docker build --build-arg LLM_BACKEND=cpu -t persistent-rag/agent:local -f "$ROOT/ai_agents_framework/ai_agent/Dockerfile" "$ROOT"
    # WORKDIR already creates /package in the upstream dispatcher Dockerfile.
    mkdir -p "$ROOT/work/persistent-rag"
    sed 's/mkdir \/package$/mkdir -p \/package/' "$ROOT/ai_agents_framework/docs_dispatcher/Dockerfile" > "$ROOT/work/persistent-rag/dispatcher.Dockerfile"
    # Preserve the upstream allowlist for the generated dispatcher Dockerfile.
    cp "$ROOT/ai_agents_framework/docs_dispatcher/Dockerfile.dockerignore" "$ROOT/work/persistent-rag/dispatcher.Dockerfile.dockerignore"
    docker build -t persistent-rag/dispatcher:local -f "$ROOT/work/persistent-rag/dispatcher.Dockerfile" "$ROOT"
    docker build -t persistent-rag/rag-base:local -f "$ROOT/ai_agents_framework/RAG/Dockerfile" "$ROOT"
    docker build -t persistent-rag/rag:local -f "$HERE/RAG.Dockerfile" "$HERE"
    docker build --build-context common="$ROOT/common" -t persistent-rag/file-uploader:local -f "$ROOT/utility/file-uploader/Dockerfile" "$ROOT/utility/file-uploader"
    docker build --build-context common="$ROOT/common" -t persistent-rag/rest-api:local -f "$ROOT/rest_api/Dockerfile.isolated" "$ROOT/rest_api"
    docker build -t persistent-rag/ai-agent-http-ambassador:local -f "$ROOT/ai_agents_framework/ai_agent_http_ambassador/Dockerfile" "$ROOT"
    docker build -t persistent-rag/http-api-gateway-controller:local -f "$ROOT/fs_api_proxy/http_api_gateway/Dockerfile.controller" "$ROOT"
    docker pull envoyproxy/envoy:v1.36.0
    docker save -o "$HERE/images.tar.tmp" persistent-rag/agent:local persistent-rag/dispatcher:local persistent-rag/rag:local \
        persistent-rag/file-uploader:local persistent-rag/rest-api:local \
        persistent-rag/ai-agent-http-ambassador:local persistent-rag/http-api-gateway-controller:local \
        envoyproxy/envoy:v1.36.0
    mv "$HERE/images.tar.tmp" "$HERE/images.tar"
    compose build
}
case "${1:-up}" in
    build) build ;;
    up) docker image inspect persistent-rag/controller:local >/dev/null 2>&1 || build; compose up -d ;;
    down) compose stop rag; compose down ;;
    logs) compose logs -f rag ;;
    *) echo "Usage: $0 [build|up|down|logs]" >&2; exit 2 ;;
esac
