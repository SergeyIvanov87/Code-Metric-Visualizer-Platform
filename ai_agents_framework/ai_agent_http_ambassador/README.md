# Example: AI-agent HTTP ambassador

This service is a concrete implementation of the generic **HTTP ambassador**
pattern. The AI agent is the **Represented Service**. The ambassador serves
schema-driven chat, single-document, and bulk file/folder pages. It forwards
requests to the existing filesystem API with the shared `APIQueryInterruptible`
client.
It adds no model dependencies and does not generate or change the represented
service's executors.

## Schema ownership and endpoints

The image copies exactly `chat.json`, `rag_add.json`, and
`rag_bulk_add.json` from the represented service. At startup, the ambassador
reads every JSON file in `schema_dir`,
validates query schemas, selects the supported schemas through
`SUPPORTED_SCHEMAS`, and fails if another file declares a query the server
does not support. Public paths and request parameter names come from those
loaded schemas rather than a second hardcoded API contract.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/api.pmccabe_collector.restapi.org/ai_agent/chat/v1` | Schema-driven chat page |
| POST | Same chat path | Forward the JSON object to the filesystem chat query |
| GET | `/api.pmccabe_collector.restapi.org/ai_agent/rag/add_doc/v1` | Schema-driven file-selection page |
| PUT | Same upload path | Forward the JSON object to the filesystem `rag_add` query |
| GET | `/api.pmccabe_collector.restapi.org/ai_agent/rag/bulk_add/v1` | Multi-file and folder-selection page |
| POST | Same bulk path | Start a deferred `rag_bulk_add` request with schema parameters |
| PUT | Same bulk path | Atomically publish one file into the request's shared staging input |
| PATCH | Same bulk path | Seal the upload, drain events, and return the final RAG result |
| GET | `/.well-known/http-api-routes/v1` | Route-discovery document |
| GET | `/healthz` | Check the supported queries' exec and result FIFOs |

Trailing slashes are accepted. Pages can render while the agent is starting;
actions return 503 when their filesystem query is unavailable. Health checks
verify FIFO presence, not model or database readiness.

The chat page derives its editable fields from the chat schema. Browser history
is tab-local and is placed in the schema-defined message parameter before the
request is sent. The upload page derives the document parameter from the
`rag_add` schema and base64-encodes the selected file into that parameter.
The ambassador forwards every received JSON key and value unchanged apart from
filesystem FIFO quoting and its internal `SESSION_ID`. The filesystem API owns
parameter validation, defaults, decoding, and operation semantics.

The bulk page accumulates repeated file and folder selections, preserves each
browser-provided relative path, and uploads files concurrently. Its collapsed
settings are generated from the bulk schema and include metadata, RAG worker
count, directory-event allow/skip expressions, and deferred lifecycle timeouts
with their schema defaults. The browser starts `rag_bulk_add` before transferring bytes. Each
HTTP `PUT` writes to a private `.incoming` name, synchronizes it, and publishes
the final path atomically. After all transfers, `PATCH` seals the underlying
`streaming_directory_events` request, drains the RAG event FIFO, and reads the
authoritative asynchronous result.

CSS and JavaScript are embedded in each response under a per-request content
security policy nonce. All pages link back to the generic REST API menu through
the configured `MAIN_MENU_PATH`.

## Request and result behavior

Schema action requests use `application/json` and contain a JSON object.
Bulk file-transfer `PUT` requests use `application/octet-stream`; their
`upload_id` and relative `path` are query parameters. Successful results retain
the filesystem API's JSON object. A result carrying `error_code` is returned
with status 502; invalid or non-object JSON also produces 502. Unavailable
filesystem I/O produces 503. An expired write or result deadline produces 504
with `completion_unknown: true`. Oversized HTTP bodies use 413 and requests are
not retried automatically.

## Configuration and filesystem sharing

Mount `config.json` and set `AI_AGENT_HTTP_CONFIG` to its path. Set
`MAIN_MENU_PATH` to the root-relative generic REST menu path. Settings:

| Setting | Default | Purpose |
| --- | --- | --- |
| `api_mount` | `/api` | Filesystem API mount inside this server |
| `schema_dir` | `/app/API` | Directory containing the copied query schemas |
| `timeout_seconds` | `900` | Overall FIFO write/read deadline |
| `max_upload_bytes` | `16777216` | Maximum JSON body or individual bulk file size |
| `max_result_bytes` | `4194304` | Maximum filesystem result size |

The agent, generic REST provider, and ambassador share the same local filesystem
API volume. The ambassador assumes configured API paths are valid; it does not
apply a separate absolute-path or shell-safety policy.

## FIFO protocol

For each loaded schema, `compose_api_queries_pipe_names` derives the query's
`exec` and `result.json` FIFOs. The ambassador constructs
`APIQueryInterruptible`, writes through its `execute` method, and reads
through its `wait_result` method. It does not open or read the FIFOs through a
private client implementation.

Requests include a generated `SESSION_ID`, and the represented service creates
`result.json_<SESSION_ID>`. Completed session identifiers are reused per HTTP
worker thread to bound normal result-FIFO accumulation. A per-query in-process
lock prevents concurrent HTTP threads from interleaving long FIFO commands.

Deferred bulk sessions additionally use the client's bounded `write_fifo`
and `read_fifo` methods for the seal, event, and asynchronous-result channels.
The generated Bash CLI server splits commands at LF before parsing quoted
arguments. The adapter therefore changes embedded LF to CR, escapes quotes and
backslashes, and rejects NUL. The shared interruptible client writes encoded
bytes so multibyte Unicode data is neither truncated nor falsely timed out.

## Route precedence and fallback

The HTTP API gateway provider order is:

1. `rest-api`, the generic catch-all provider;
2. `ai-agent-http-ambassador`, which advertises the three schema-derived
   action paths and therefore owns those overlaps.

Unadvertised paths continue to fall back to `rest-api`.

## Run

Use the [HTTP API gateway deployment](../../fs_api_proxy/http_api_gateway/README.md)
to expose these pages alongside the generic API. From the repository root:

```sh
docker compose -f ai_agents_framework/ai_agent_http_ambassador/compose.yaml up -d --build
```

For a local Python process, install `requirements.txt`, adjust a copy of
`config.json`, and run:

```sh
AI_AGENT_HTTP_CONFIG=/absolute/path/to/config.json \
  gunicorn --config gunicorn.conf.py 'server:create_app()'
```

## Tests

From the repository root:

```sh
python3 -m venv work/http-venv
work/http-venv/bin/pip install -r ai_agents_framework/ai_agent_http_ambassador/requirements-test.txt
work/http-venv/bin/python -m pytest -q ai_agents_framework/ai_agent_http_ambassador/tests
```

The focused tests exercise schema loading, generic parameter forwarding,
Unicode and multiline FIFO framing, concurrent writes, session reuse, bounded
timeouts, result validation, single and parallel bulk upload forwarding,
atomic relative-path publication, sealing, filter defaults, discovery, and
unavailable queries. Envoy forwarding tests run when `ENVOY_BINARY` is
configured.
