# Persistent RAG using Docker out of Docker

From the repository root, run:

```sh
./Dood/persistent_RAG/launch.sh
```

Requires Docker Engine, Compose v2 (with `up --wait`), Linux/amd64, and enough disk/RAM for the CPU inference image. The first launch builds the framework images and packages them in the controller. Builds require Internet access. Subsequent launches use the packaged images.

The only deployment setting is the **Docker named volume for the filesystem API**:

```sh
FS_API_VOLUME=my-filesystem-api ./Dood/persistent_RAG/launch.sh
```

Defaults to `persistent-rag-api`. An existing named volume is reused; otherwise it is created automatically. Use the same setting for later commands. This setting is a volume name, not a host directory. Mount that volume in filesystem API consumers at `/api`. Application API paths remain under `/api/api.pmccabe_collector.restapi.org/`. The initializer gives shared group 23456 write access to the volume root without recursively changing existing files.

```sh
./Dood/persistent_RAG/launch.sh build # rebuild after source changes
./Dood/persistent_RAG/launch.sh logs
./Dood/persistent_RAG/launch.sh down
```

After building, the minimal deployment is `docker compose -f Dood/persistent_RAG/compose.yaml up -d`. To deploy independently of this repository, transfer the built `persistent-rag/controller:local` image using Docker save/load, plus `compose.yaml`; run `docker compose up -d --no-build`. The controller contains the three application images and internal Compose definition. The source folder alone supports rebuilds when located in this repository.

The public Compose file runs the controller and `tecnativa/docker-socket-proxy`. The controller imports its images and creates the sibling containers, their network, and all named storage volumes. The agent waits for Chroma and the dispatcher. The dispatcher uses the existing SQLite backend; no separate MySQL server or credentials are needed. Chroma is explicitly persisted at `/mnt/chroma` and launched without the original password-enabled SSH bootstrap. No service ports or Docker API ports are published. Logs use Docker's default logging driver, so no external syslog stack is required.

Application containers cannot join the private control network or access the socket proxy. Only the proxy mounts the host socket. API categories needed for container/image/network/volume lifecycle and POST are enabled; build, exec, auth, secrets, and swarm operations are disabled. This reduces exposed API surface but is not a full security boundary: container creation and image import are powerful host-level permissions, and a read-only socket mount does not make API operations read-only. Treat the controller and proxy as trusted components.

Stopping the controller removes its siblings and network while preserving named volumes. Internal containers restart after daemon restarts, and the controller reconciles the stack periodically. Storage has a fixed `persistent-rag` project name; one deployment per Docker daemon is supported. The framework downloads embedding and Qwen model weights on first use; building the image does not bundle model weights. Inference requires Internet access to Hugging Face and enough RAM for the CPU model. Persistent `/package` and dispatcher configuration volumes are initialized from the images on first use; rebuilding images does not overwrite existing volumes. Inspect/migrate those volumes when updating source/configuration.

## CI and functional tests

`.github/workflows/dood_ai_persistent_rag.yml` has separate build and functional jobs. The build job packages the application images and exports the controller as an artifact. The functional job loads that exact image, starts it through the production socket proxy, waits for internal stack readiness, and runs the existing `ai_agent_rag_functional_tester` against the shared filesystem API. Only the tester service definition is duplicated; its Dockerfile, fixtures, and Python tests remain shared with the framework. This avoids inheriting dependencies that would start a second application stack.

After building the controller, run locally:

```sh
export COMPOSE_FILE=Dood/persistent_RAG/tests/functional/compose-test-functional.yml
docker compose build ai_agent_rag_functional_tester
docker compose up -d --no-build --wait --wait-timeout 900 rag
docker compose run --rm --no-deps ai_agent_rag_functional_tester
docker compose stop rag
docker compose -f Dood/persistent_RAG/stack.yaml down --volumes
docker compose down --volumes
```

These cleanup commands delete test storage. Use a dedicated daemon or fresh volumes for tests: the grounded-chat assertions assume an empty knowledge base. Tests use real embedding/inference models, including first-use downloads, rather than mocks. CI collects controller and sibling logs even on failures. The controller's health check reports readiness after the internal `compose up --wait` succeeds.

CPU/Intel production agent builds select PyTorch from the CPU wheel index before installing sentence-transformers, constrain that wheel during dependency resolution, and disable pip caching. NVIDIA builds retain their existing PyTorch selection. CI verifies the DooD agent contains CPU-only PyTorch, no NVIDIA Python packages, and no root pip cache before exporting the controller.
