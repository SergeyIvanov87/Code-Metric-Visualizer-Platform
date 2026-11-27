`LOCAL_HOST_MOUNT_POINT=<local host mount point> && mkdir -p ${LOCAL_HOST_MOUNT_POINT} && chmod 777 ${LOCAL_HOST_MOUNT_POINT} && docker volume create -d local -o type=none -o device=${LOCAL_HOST_MOUNT_POINT} -o o=bind api.pmccabe_collector.restapi.org`
`SRC_MOUNT_POINT=ai_agent/sources  && docker volume create -d local -o type=none -o device=${SRC_MOUNT_POINT} -o o=bind api.pmccabe_collector.ai_agent.src`
`RAG_ASSETS_MOUNT_POINT=<RAG assets storage path> && mkdir -p ${RAG_ASSETS_MOUNT_POINT} && chmod 777 ${RAG_ASSETS_MOUNT_POINT} && docker volume create -d local -o type=none -o device=${RAG_ASSETS_MOUNT_POINT} -o o=bind api.pmccabe_collector.ai_agent.asssets.rag`

`docker build -t ai_agent:latest -f ai_agent/Dockerfile .`
`docker run -it --name ai_agent -v api.pmccabe_collector.restapi.org:/api -v api.pmccabe_collector.ai_agent.asssets.rag:/assets/rag -v api.pmccabe_collector.ai_agent.src:/package ai_agent:latest`

## Service API dependencies

`API/deps` declares the filesystem APIs used by the agent: the document
dispatcher's `put_doc`, `attach_doc_chunk`, `delete_doc`, `get_docs`, `read_id`,
and `sync`, plus the file uploader's `streaming_directory_events`.

The agent exposes `ai_agent/all_dependencies/GET` and
`ai_agent/unmet_dependencies/GET` under `api.pmccabe_collector.restapi.org`.
Startup launches the business and dependency command APIs with the shared
unprivileged helpers. When `SKIP_API_DEPS_CHECK=false`, it waits for the declared
providers before publishing the ready message and README. Images and base
Compose models default to `SKIP_API_DEPS_CHECK=false` and
`TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC=30`. The latter is a retry count in
the shared helper, despite its `SEC` suffix. Container environment variables
and Compose interpolation can override these settings.

Both business and command schemas are registered with the API cleanup manager.
Startup, API generation, and cleanup run as the service user. Generated files
are stored in `/mnt/generated`, leaving startup writes off development source
mounts. The Docker images retain their existing user and package setup; runtime
scripts do not use superuser privileges.

Functional and streaming testers keep their own users and wait on the real
agent's `unmet_dependencies` endpoint before running tests. They write requests
to `exec` (mode `0622`) and read `result*` (mode `0644`); method directories remain
`0755`. The shared dependency test checks live provider availability without
replacing foreign-owned FIFOs. Outage mutation remains covered using tester-owned
fixtures in the existing common regression tests.

The Chroma HTTP service remains a separate runtime prerequisite configured by
`VECTORDB_HOST` and `VECTORDB_PORT`; the shared filesystem dependency checker
checks filesystem APIs.

## Chat inference moved to ai_chat_agent

This service handles document ingestion, chunking, embeddings, deletion, and
reconciliation. Embeddings use CPU. Its images no longer install llama.cpp,
LLM orchestration, CUDA build tools, or Vulkan drivers. The existing NVIDIA and
Vulkan Compose profiles retain their proxy settings, build arguments, inference
configuration mounts, and device access declarations.

Chat sources, inference profiles, and the chat API schema now live under
`../ai_chat_agent`. Model assets and inference configuration belong there.

Run RAG functional test cases from the repository root:

```sh
docker compose -f ai_agents_framework/ai_agent/compose-functional.test.yaml up --build --abort-on-container-exit --exit-code-from ai_agent-functional-tester
```
