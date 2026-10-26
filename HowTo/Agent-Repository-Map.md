# Repository knowledge map for agents

This map was derived from the code, API schemas, Compose models, tests, and CI on `origin/main` at `2569e2c`. It is a navigation aid, not a claim that every service was run. Follow current source when this snapshot drifts.

## Architecture and ownership

| Area | Responsibility | Start here |
| --- | --- | --- |
| Common filesystem API | Schema parsing, generated executors/listeners, query sessions and cleanup | [common](../common), especially `modules`, `build_api_services.py`, `build_api_executors.py`, `api_management.py` |
| Cyclomatic complexity | C/C++ file selection, statistics, text/SVG flamegraphs | [schemas](../cyclomatic_complexity/API), [generator](../cyclomatic_complexity/api_generator.py) |
| RRD analytics | Metric collection, round-robin persistence, CSV/plots | [schemas](../rrd_analytic/API), [generator](../rrd_analytic/api_generator.py), `build_rrd.py`, `fetch_rrd.py`, `graph_rrd.py` |
| VCS and scheduling | Repository updates and ordered scheduled calls | [VCS](../observable_project_version_control), [broker scheduler](../service_broker/build_schedule_jobs.py), broker `API/deps` |
| HTTP transport | HTTP exposure, discovered route ownership, dynamic gateway routing and remote proxying | [REST server](../rest_api/rest_api_server/rest_api_server), [HTTP API gateway](../fs_api_proxy/http_api_gateway), [proxy](../fs_api_proxy/http_proxy) |
| Streaming ingestion | Deferred file transfer, directory transfer, shared-staging readiness | [upload protocol](../utility/file-uploader/README.md), uploader `API` and processor modules |
| Agentic RAG | Document/chunk storage, embeddings, retrieval and inference | [agent sources](../ai_agents_framework/ai_agent/sources), [dispatcher sources](../ai_agents_framework/docs_dispatcher/sources), [vector store stack](../ai_agents_framework/RAG) |
| Test observability | Legacy log aggregation and streaming tap/event analysis | [legacy implementation](../common/images/test_aggregator_image), [streaming documentation](../common/images/streaming_test_aggregator/README.md) |
| Kubernetes | Deployment manifests and a separate CI execution path | [deployment guidance](../k8s/README.md), [workflow](../.github/workflows/minikube.yml) |

### Stack selection

- [Analysis](../compose-analysis.yaml): measures a locally mounted project (`PROJECT_PATH`).
- [Analytic](../compose-analytic.yaml): adds VCS/broker orchestration, scheduled measurements, and persistent RRD storage (`PROJECT_URL`, `PROJECT_BRANCH`, optional `CRON_REPO_UPDATE_SCHEDULE`).
- [Analysis over HTTP](../compose-analysis-http-api.yaml) and [Analytic over HTTP](../compose-analytic-http-api.yaml): inspect proxy and transport boundaries as well as providers.
- [Agentic RAG](../ai_agents_framework/compose.rag-agent.yaml) and [streaming variant](../ai_agents_framework/compose.rag-agent.streaming.yaml): distinct agent/document/vector-store topology.

Root [README prerequisites](../README.md#prerequisites) describe external API, logger and RRD volumes and shared network requirements. Inspect the chosen Compose model before creating resources. Historical setup examples include broad permissions and daemon changes; these are not necessary for reading code or authoring skills.

The current dynamic provider-discovery, route-precedence, generic Envoy, and
HTTP ambassador design is described in the [REST API customization implementation
record](../Architecture_Design_Decisions/Rest-API-Customization/implementation_v1.md).

## Filesystem API contract

Schemas declare `Method`, `Query`, `Content-Type`, `Params`, and descriptions. Shared code interprets these and service-specific generators provide implementations. Runtime paths and scripts are generated: fix source schemas/generators rather than a disposable generated artifact.

Read these in order for API changes:

1. The owning service's `API/*.json` and `api_generator.py` (or upload processor).
2. [Schema parsing](../common/modules/api_schema_utils.py), [path conventions](../common/modules/api_fs_conventions.py), [arguments](../common/modules/api_fs_args.py).
3. [API construction](../common/build_api_services.py), [executors](../common/build_api_executors.py), [query client](../common/modules/api_fs_query.py).
4. [Deferred launcher](../common/deferred_query_launcher.py) and [executor](../common/deferred_query_executor.py) when work outlives the initial request.
5. Consumers' `API/deps` and the [REST adapter](../rest_api/rest_api_server/rest_api_server).

`exec` and result nodes are FIFOs, not ordinary files. Requests are newline framed. A session-specific result must be paired with its `SESSION_ID`. Generated GUI listeners use filesystem access/modify events in addition to CLI FIFO requests. Deferred handshakes publish request channels; the final asynchronous result determines processing success. See the [human API guide](How-To-Use-API.md) for background and current tests for lifecycle details.

Directory events and directory uploads have deliberately different data ownership. [The upload README](../utility/file-uploader/README.md) specifies persistent shared staging versus request-scoped input, batched JSON-Line events, explicit sealing, final results, filtering, and limits. [The parser](../common/modules/directory_event_protocol.py) validates increasing sequence numbers and batch bounds.

## Agentic RAG

Start with [wrappers](../ai_agents_framework/ai_agent/sources/fs_api_wrappers.py), then the matching dispatcher entrypoint and backend command. The dispatcher selects its backend through [configuration code](../ai_agents_framework/docs_dispatcher/sources/dispatcher_backend_config.py) and [backend specs](../ai_agents_framework/docs_dispatcher/sources/backend/dispatcher/README.md). The `mysql` package name does not imply a live MySQL server: its default URI is SQLite.

[Reconciliation](../ai_agents_framework/ai_agent/sources/rag_sync.py) maps dispatcher chunk records to Chroma IDs and metadata. Keep stale-ID deletion after successful source enumeration, including all pages. Focused tests exercise fake collections; service tests are still needed for live storage integration.

[Inference configuration](../ai_agents_framework/ai_agent/sources/inference_config.py) and [runtime documentation](../ai_agents_framework/ai_agent/README.md) cover CPU, NVIDIA and Intel Vulkan. Agent-only GPU Compose files require an accessible vector store and dispatcher setup. Model downloads, hardware access and per-replica memory budgets are deployment prerequisites, not assumptions for unit tests.

## Test matrix

Commands run from the repository root. CI definitions are the source for setup and orchestration; the root README contains older testing descriptions. A command below identifies a scope, not a promise that its Docker prerequisites are installed.

| Scope | Entry point | Status authority |
| --- | --- | --- |
| Common deferred transport | `python -m pytest -q common/test_deferred_query_executor.py` | pytest |
| Directory event parser | `python -m pytest -q common/test_directory_event_protocol.py` | pytest |
| Agent isolated behavior | `python -m pytest -q ai_agents_framework/ai_agent/tests` | pytest; inspect optional dependencies |
| Common API lifecycle | `common/images/unit_test/compose.yaml` | `unit_tests` |
| File uploader | `utility/file-uploader/compose-functional.test.yaml` | `file-uploader-functional-tester` |
| Cyclomatic complexity | `cyclomatic_complexity/compose-functional.test.yaml` | `cc-functional-tester` |
| RRD | `rrd_analytic/compose-functional.test.yaml` | `rrd-functional-tester` |
| REST | `rest_api/compose-functional.test.yaml` | `rest-api-functional-service-tester` |
| Broker | `service_broker/compose-functional.test.yaml` | `service-broker-functional-tester` |
| Dispatcher | `ai_agents_framework/docs_dispatcher/compose-functional.prod.yaml` | `docs-dispatcher-functional-tester` |
| Vector store | `ai_agents_framework/RAG/compose-functional.test.yaml` | `rag-functional-tester` |
| All isolated services | `compose-functional.test.yaml` | `test_aggregator` |
| Running Analysis/Analytic integration | `compose-analysis.integrational-test.yaml` | `test_aggregator`; start the selected stack first |
| Streaming event pipeline | `common/images/streaming_test_aggregator/tests/functional/compose-functional.test.yaml` | aggregator, then `functional-tests`; detached orchestration |
| Agent and RAG with streaming capture | `ai_agents_framework/tests/streaming/compose.agent.rag-agent.streaming.tests.yaml` | follow the dedicated workflow |
| Agent, RAG, and discovered HTTP gateway with streaming capture | `ai_agents_framework/tests/streaming/compose.agent.rag-agent.http.streaming.tests.yaml` | HTTP smoke checks, filesystem tester, then authoritative aggregator result |

Example finite service suite:

```sh
docker compose -f utility/file-uploader/compose-functional.test.yaml config --quiet
docker compose -f utility/file-uploader/compose-functional.test.yaml up --build --abort-on-container-exit --exit-code-from file-uploader-functional-tester
```

For image-only changes, inspect Dockerfile `COPY` sources and Compose `build.context`; many builds copy shared `common` files and need repository-root context. Do not assume the Dockerfile directory is the build context.

### CI and diagnostics references

- [Main Docker CI](../.github/workflows/docker-image.yml): common lifecycle, service functional, combined and use-case tests.
- [Agentic RAG CI](../.github/workflows/agentic-rag-subsystem.yml): dispatcher/vector-store builds and tests.
- GPU agent image builds: independent [NVIDIA](../.github/workflows/ai-agent-nvidia-image.yml) and [Vulkan](../.github/workflows/ai-agent-vulkan-image.yml) workflows compile production/development images in parallel, with cached builds and manual dispatch. These checks do not validate GPU runtime behavior.
- [Streaming pipeline CI](../.github/workflows/streaming-test-aggregator.yml): detached launch, aggregator status, final checks, diagnostic export.
- [Streaming integration CI](../.github/workflows/streaming-test-aggregator-integration.yml) and [agent streaming CI](../.github/workflows/agentic-rag-streaming-test-aggregator-integration.yml).
- [Agentic RAG HTTP streaming CI](../.github/workflows/agentic-rag-http-streaming-test-aggregator-integration.yml): builds all stack, logger, and aggregator images before launching and testing the discovered HTTP topology.
- [Streaming lifecycle](../common/images/streaming_test_aggregator/README.md): permanent logger, on-demand capture IDs and one active subscriber constraint.
- [Capture event schema](../common/images/streaming_test_aggregator/tap_subscriber/EVENT_SCHEMA.md).
- [Legacy artifact action](../.github/actions/upload-test-aggregator-artifacts/action.yml).

Preserve exit codes and logs before cleanup. A transient broker readiness delay is different from Envoy terminating because of an invalid admin sink format. Diagnose the earliest failed stage. Do not copy CI-wide Docker pruning onto a shared developer host.
