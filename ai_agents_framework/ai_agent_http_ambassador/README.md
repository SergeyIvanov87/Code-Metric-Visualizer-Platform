# Example: AI-agent HTTP ambassador

This service is a concrete implementation of the generic **HTTP ambassador**
pattern. The AI agent is the **Represented Service** in this example. The
ambassador provides chat and document-upload pages and calls the existing
`ai_agent` filesystem API. It adds no model dependencies and does not generate
or change the Represented Service's executors. Flask handles HTTP, Gunicorn
serves requests, and `fifo_client.py` adapts them to the existing `exec` /
`result.json` FIFO protocol.

“Ambassador” is the usual term for a service companion that handles connectivity
or protocol adaptation for a Represented Service. In this example, the source
directory is `ai_agent_http_ambassador` and the container service is
`ai-agent-http-ambassador`.

## Endpoints

The image copies exactly `chat.json` and `rag_add.json` from the represented
service. At startup, the ambassador reads every JSON file that exists in the
configured `schema_dir` and reports an error if any file declares a query that
the server does not support. No default prompt is maintained separately.
Rebuild the image after changing either supported schema, or mount a schema
directory containing only supported query files. The gateway discovers route
paths from the ambassador; no Envoy-specific path list is maintained here.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/api.pmccabe_collector.restapi.org/ai_agent/chat/v1` | Chat page |
| POST | Same chat path | JSON chat request → filesystem chat |
| GET | `/api.pmccabe_collector.restapi.org/ai_agent/rag/add_doc/v1` | File selection page |
| PUT | Same upload path | Raw UTF-8 file bytes → staging → filesystem rag_add |
| GET | `/.well-known/http-api-routes/v1` | JSON route-discovery document |
| GET | `/healthz` | Check both queries' exec and result FIFOs |

Trailing slashes are accepted. GET pages can load while the agent is starting;
actions return 503 when the required FIFOs are unavailable. HEAD follows Flask's
standard GET behavior; it does not execute an agent keep-alive query. Health
checks verify FIFO presence, not model/database readiness.

The chat page has a multiline message field, a Submit button and a scrolling,
read-only history field. The system prompt starts with the schema's
`Params.-system_prompt`, with CLI grouping quotes removed. Its multiline editor
is inside a collapsed-by-default `<details>` panel. Submitting uses POST.
The existing chat API has no persistent conversational memory: this page keeps
successful turns in the browser tab and sends them as context in `user_prompt`.
Refreshing starts a new history, and history counts against the prompt limit.
The CSS and JavaScript are embedded in each response under a per-request content
security policy nonce, so no ambassador-private static path is exposed.
Both pages put a **Return to the main menu** link first in their navigation. Its
root-relative `/api.pmccabe_collector.restapi.org` target keeps the current HTTP
host and port and returns to the generic REST API menu through the dispatcher.

The file input opens the browser's standard selection dialog. Selection sends a
PUT immediately. The current agent reads UTF-8 text and supports `txt` chunking;
this adapter accepts text files such as `.txt` and `.md` and rejects invalid
UTF-8 bytes. The original bytes, including LF line endings, are staged unchanged.
It does not add PDF, binary, or word-processing-document ingestion to the agent.

HTTP examples:

```sh
curl -X POST http://localhost:8080/api.pmccabe_collector.restapi.org/ai_agent/chat/v1 \
  -H 'Content-Type: application/json' \
  -d '{"user_prompt":"What is the RRD microservice?"}'

curl -X PUT http://localhost:8080/api.pmccabe_collector.restapi.org/ai_agent/rag/add_doc/v1 \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @README.md
```

POST accepts `user_prompt` and optional `system_prompt`; an omitted system prompt
uses the schema default. PUT takes the file itself as its body, rather than
multipart form data or a caller-supplied server path. The adapter uses generated
safe filenames and metadata. Successful results retain the agent's JSON format
(`response` for chat, `doc_id` and `chunk_ids` for rag_add). Backend errors or
invalid JSON produce 502; unavailable filesystem I/O produces 503; an expired
FIFO deadline produces 504 with `completion_unknown: true`. Client validation
errors use 400/413/415. Requests are not retried automatically.

## Configuration and filesystem sharing

Mount `config.json` and set `AI_AGENT_HTTP_CONFIG` to its path. Set
`MAIN_MENU_PATH` to the exact root-relative generic REST menu path; the Docker
image and Compose model default it to `/api.pmccabe_collector.restapi.org`.
Settings:

| Setting | Default | Purpose |
| --- | --- | --- |
| `api_mount` | `/api` | Filesystem API mount inside this server |
| `agent_api_mount` | `/api` | The same mount's path inside ai_agent |
| `schema_dir` | `/app/API` | Directory with chat.json and rag_add.json |
| `timeout_seconds` | `900` | Overall FIFO write/read deadline, including contention |
| `max_upload_bytes` | `16777216` | 16 MiB HTTP body/file limit |
| `max_prompt_bytes` | `65536` | Combined UTF-8 user/system prompt limit |
| `max_result_bytes` | `4194304` | 4 MiB filesystem result limit |

The mount must allow this container to write `exec` and create its temporary
subdirectory. Its user is UID 2002, group 23456, consistent with the project's
shared group. The agent must be able to read the staged files. Request
directories are mode 755 and files mode 644, independently of the server's
umask. API mount paths must be absolute and use shell-safe characters because
the existing rag_add executor runs a shell command. If the agent mounts the
volume at `/agent-api`, for example, set `agent_api_mount` accordingly while
keeping `api_mount` at `/api`.

Files are staged under `/api/.http_ambassador/staging/<random-id>/document.txt`,
outside the API domain tree scanned by `rest_api`. `rag_add` is called with
`-URI` pointing to that file in the agent's mount, `-doc_type=txt`, and generated
`-metadata`. No original filename or arbitrary user metadata is passed to its
shell executor. After receiving a result the staging directory is removed.
If completion is uncertain after a deadline/I/O failure, the file is retained
so a queued agent operation can still read it. Remove such retained directories
only after the corresponding operation is known to have finished or the agent
has been stopped. The adapter cannot cancel the unmodified agent's operation.

## FIFO protocol details

Both queries use `<api_mount>/<Query>/<Method>/exec` and a base `result.json`
FIFO. Requests include a generated `SESSION_ID`, and the agent creates
`result.json_<SESSION_ID>` for the response. The client uses nonblocking I/O
and a monotonic deadline for stalled writers, delayed result creation and
stalled readers. It verifies that paths are FIFOs and never creates, replaces
or unlinks the agent's pipes. Completed sessions are reused per HTTP worker
thread to bound normal result-FIFO/map accumulation; failed sessions are
abandoned to avoid consuming a previous request's late result. Those abandoned
artifacts remain owned by the agent.

The generated Bash CLI server splits incoming commands at LF **before** parsing
quoted arguments. Consequently, embedding LF in a FIFO value would dispatch
multiple broken commands. The adapter normalizes CRLF and represents prompt
line breaks as CR within double-quoted values. The agent receives carriage-return
line separators, preserving multiline prompt layout without modifying its code.
Quotes and backslashes are escaped for the project's quote-aware parser, not
interpreted as shell commands. NUL and invalid Unicode are rejected. This line
ending adaptation applies to prompts, not staged document content.

Long commands may exceed the FIFO's atomic write size. A filesystem lock per
query serializes writes across the adapter's threads/processes/replicas; each
result is read through its own session. Independent direct-FIFO writers need
to coordinate with these locks to avoid interleaving long writes. The existing
agent serializes execution within each query and its Bash argument parsing can
be slow on very large prompts. HTTP worker concurrency does not make inference
or ingestion parallel inside the agent.

## Run

Use the [HTTP API gateway deployment](../../fs_api_proxy/http_api_gateway/README.md)
to discover and expose both pages alongside the existing generic API. From the repository
root the ambassador alone can be started with:

```sh
docker compose -f ai_agents_framework/ai_agent_http_ambassador/compose.yaml up -d --build
```

`HTTP_BIND` changes Gunicorn's listening address/port (default `0.0.0.0:8081`).
The Compose example keeps port 8081 inside the Docker network. Publish it through
a new Compose override if a remote dispatcher needs direct access. The agent,
generic server and ambassador share one local volume; FIFOs require local
filesystem semantics. A router on a different machine only needs HTTP access.

For a local Python process, install `requirements.txt`, adjust the paths in a
copy of `config.json`, and run from this directory:

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

Tests run the project's actual generated Bash CLI servers and the chat/rag_add
executors. Only the heavy inference and ingestion Python programs are replaced
with lightweight stubs. They exercise prompt escaping/line breaks, Unicode,
concurrent writes above PIPE_BUF, session reuse, shared staging, mount-path
mapping, cleanup, size limits, invalid uploads/results and unavailable APIs.

To include the real Envoy HTTP forwarding tests, install Envoy and set its path:

```sh
ENVOY_BINARY=/absolute/path/to/envoy work/http-venv/bin/python -m pytest -q \
  ai_agents_framework/ai_agent_http_ambassador/tests
```

These tests start loopback HTTP services, generate the same bootstrap and RDS
resources as the gateway controller, and send real GET/POST/PUT requests through
Envoy. They do not
require a model, vector database, or running production services.
