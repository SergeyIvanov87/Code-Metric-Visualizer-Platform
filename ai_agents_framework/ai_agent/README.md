`LOCAL_HOST_MOUNT_POINT=<local host mount point> && mkdir -p ${LOCAL_HOST_MOUNT_POINT} && chmod 777 ${LOCAL_HOST_MOUNT_POINT} && docker volume create -d local -o type=none -o device=${LOCAL_HOST_MOUNT_POINT} -o o=bind api.pmccabe_collector.restapi.org`
`SRC_MOUNT_POINT=ai_agent/sources  && docker volume create -d local -o type=none -o device=${SRC_MOUNT_POINT} -o o=bind api.pmccabe_collector.ai_agent.src`
`MODEL_ASSETS_MOUNT_POINT=<artefacts storage path> && mkdir -p ${MODEL_ASSETS_MOUNT_POINT} && chmod 777 ${MODEL_ASSETS_MOUNT_POINT} && docker volume create -d local -o type=none -o device=${MODEL_ASSETS_MOUNT_POINT} -o o=bind api.pmccabe_collector.ai_agent.asssets.models`
`RAG_ASSETS_MOUNT_POINT=<RAG assets storage path> && mkdir -p ${RAG_ASSETS_MOUNT_POINT} && chmod 777 ${RAG_ASSETS_MOUNT_POINT} && docker volume create -d local -o type=none -o device=${RAG_ASSETS_MOUNT_POINT} -o o=bind api.pmccabe_collector.ai_agent.asssets.rag`

`docker build -t ai_agent:latest -f ai_agent/Dockerfile .`
`docker run -it --name ai_agent -v api.pmccabe_collector.restapi.org:/api -v api.pmccabe_collector.ai_agent.asssets.rag:/assets/rag -v api.pmccabe_collector.ai_agent.asssets.models:/assets/models -v api.pmccabe_collector.ai_agent.src:/package ai_agent:latest`

## Service API dependencies

`API/deps` declares the filesystem APIs used by the agent: the document
dispatcher's `put_doc`, `attach_doc_chunk`, `delete_doc`, `get_docs`, `read_id`,
and `sync`, plus the file uploader's `streaming_directory_events`.

The agent exposes `ai_agent/all_dependencies/GET` and
`ai_agent/unmet_dependencies/GET` under `api.pmccabe_collector.restapi.org`.
When `SKIP_API_DEPS_CHECK=false`, startup waits for the declared APIs to respond
before publishing the agent's document and chat APIs. Both images and base
Compose models default to
`SKIP_API_DEPS_CHECK=false` and
`TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC=30`, following the service broker's
dependency-check settings. The latter controls a retry count in the shared
helper, despite its `SEC` suffix; it is not an overall seconds deadline.
These settings can be overridden through container environment variables or
Compose environment interpolation. Dependency-report endpoints are included in
API cleanup. The ready message and README are published only after keep-alive
probes succeed for the agent's own APIs, including its dependency reports.
Both API managers use `--deferred-query-root` to restrict deferred-request
cleanup to the agent's subtree, preserving requests owned by providers.

Existing functional and streaming testers wait for dependency readiness and the
agent's own API initialization before running tests. Each wait is bounded by
`AI_AGENT_READY_TIMEOUT_SEC` (default `120`).

The Chroma HTTP service remains a separate runtime prerequisite configured by
`VECTORDB_HOST` and `VECTORDB_PORT`; the shared filesystem dependency checker
checks filesystem APIs.

## LLM acceleration

Run these commands from `ai_agents_framework/ai_agent`:

```sh
# Legacy CPU inference
 docker compose -f compose-default.prod.yaml up -d --build --scale ai_agent=2
# NVIDIA CUDA inference
 docker compose -f compose-default.prod.nvidia.yaml up -d --build --scale ai_agent=2
# Intel integrated graphics through Vulkan (Linux)
 export INTEL_RENDER_DEVICE=/dev/dri/renderD128
 export INTEL_RENDER_GID=$(stat -c '%g' "$INTEL_RENDER_DEVICE")
 docker compose -f compose-default.prod.vulkan.yaml up -d --build --scale ai_agent=2
```

The GPU variants extend the CPU production agent service, preserve its API/model volumes,
and allow multiple replicas without fixed container names or ports. They require
an accessible `rag-db:8000` and the existing API dispatcher setup on the same
Compose network. To use an external database, add an override for `VECTORDB_HOST`
and `VECTORDB_PORT`. To join an existing stack, add its network in an override.
The supplied files launch agents only.

NVIDIA hosts need a compatible NVIDIA driver and NVIDIA Container Toolkit
configured for Docker. The image compiles llama.cpp with CUDA 12.6; the host
must support this CUDA runtime. Intel hosts need a supported Intel Vulkan GPU
and the Linux i915/xe driver; the image installs Mesa Vulkan drivers. Only the
selected render node is passed into each container, and its host group ID gives
the non-root agent access. Intel graphics use shared system memory rather than
8 GB of dedicated VRAM. Older Intel GPUs without the required Vulkan features
are not supported by this backend.

`config/inference.cpu.json`, `config/inference.nvidia.json`, and
`config/inference.intel.json` configure accelerator, GPU index, offloaded layers,
context size, batch size, and CPU threads (`null` selects CPU count minus one).
Compose mounts this directory read-only. Set `AI_AGENT_INFERENCE_CONFIG` to a
custom JSON file to select another configuration. Direct execution defaults to
the CPU profile; the original production/development Compose files remain CPU
by default. Development GPU builds use the same `BASE_IMAGE` and `LLM_BACKEND`
build arguments with `Dockerfile.dev`, plus the runtime configuration and device
settings from the matching GPU Compose file.

GPU profiles offload all layers of the existing Qwen3-4B Q4_K_M model and use an
8192-token context with batch size 256, targeting an 8 GB memory budget. Actual
memory use depends on the model, context, backend, and concurrent requests.
Each replica loads its own model and KV cache: two replicas share the same GPU
and may exceed 8 GB. Start with one replica, check memory usage, then scale.
Reduce `n_ctx`/`n_batch` or set a positive `n_gpu_layers` for partial offloading
if necessary. GPU mode rejects CPU-only builds, absent devices, and non-Intel
Vulkan devices. It does not silently select CPU mode. llama.cpp's verbose load
logs show layer offloading; verify these on the target host.

The llama-cpp-python version is pinned to 0.3.16 because backend device checks
use its bundled ggml C API. Upgrading it requires rechecking that API.

Both Dockerfiles pass `-DLLAVA_BUILD=OFF` for the current text-only Qwen agent.
In llama-cpp-python 0.3.16 this disables the optional multimodal library and its
CLI tools, including `llama-mtmd-cli`, which otherwise builds even with
`LLAMA_BUILD_TOOLS=OFF`. The core inference library and selected GPU backend
remain enabled. Image/audio inference requires revisiting this setting.

NVIDIA builds use the CUDA development image's toolkit and its bundled driver
stub through the normal CUDA build configuration. No temporary driver symlink or
extra executable linker search path is added. NVIDIA Container Toolkit must
supply the real host driver library when the container runs.

GPU image compilation is checked by the independent `AI Agent NVIDIA Image Build`
and `AI Agent VULKAN Image Build` GitHub Actions workflows. Each builds production
and development images in parallel jobs, uses a separate BuildKit cache per
backend and variant, and supports manual dispatch. Automatic runs cover pull
requests to `main` and pushes to `main` affecting agent sources, shared `common`
files, or the corresponding workflow. These checks require no GPU and do not
validate hardware access or model offloading.
