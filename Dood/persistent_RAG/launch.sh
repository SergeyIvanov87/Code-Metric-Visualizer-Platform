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
    docker build -t persistent-rag/dispatcher:local -f "$ROOT/work/persistent-rag/dispatcher.Dockerfile" "$ROOT"
    docker build -t persistent-rag/rag-base:local -f "$ROOT/ai_agents_framework/RAG/Dockerfile" "$ROOT"
    docker build -t persistent-rag/rag:local -f "$HERE/RAG.Dockerfile" "$HERE"
    docker save -o "$HERE/images.tar.tmp" persistent-rag/agent:local persistent-rag/dispatcher:local persistent-rag/rag:local
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
