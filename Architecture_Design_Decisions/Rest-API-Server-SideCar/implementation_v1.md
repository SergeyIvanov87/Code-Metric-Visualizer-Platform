# REST API server sidecar: implementation v1

## Purpose

The `rest_api` container is an ambassador sidecar for services that expose the
project's filesystem API. It does not own the business operations. Instead, it
discovers the filesystem API currently published in the shared `/api` volume
and exposes that snapshot as HTTP routes.

The sidecar has four responsibilities:

1. discover API endpoints, parameters, result types, and documentation;
2. restore that discovery result into a local, immutable schema snapshot;
3. generate Flask query processors from the snapshot; and
4. restart the generated HTTP server when the published filesystem API changes.

The filesystem API remains the source of truth. The generated Flask application
is a disposable projection of one observed filesystem snapshot.

## Main components

| Component | Responsibility |
| --- | --- |
| `rest_api/init.sh` | Starts the watchdog, observes Markdown API changes, and requests server restarts. |
| `rest_api/watchdog_server.sh` | Restores a filesystem snapshot, generates the Flask application, starts it, and restarts it after termination. |
| `common/restore_api_from_pseudo_fs.py` | Converts the live filesystem tree into JSON schemas plus one combined `index.md`. |
| `common/modules/api_schema_utils.py` | Traverses the tree and infers methods, query paths, parameters, content types, and FIFO names. |
| `rest_api/build_api_cgi.py` | Generates one Flask route/query processor per restored JSON schema. |
| `rest_api/rest_api_server/rest_api_server/cgi_template.py` | Supplies shared Flask imports, request accounting, and signal handling. |
| `common/modules/api_fs_query.py` | Sends framed requests to `exec` FIFOs and receives results from session FIFOs. |

## Filesystem API contract

An API provider publishes a directory tree below the configured domain,
normally:

~~~text
/api/
└── api.pmccabe_collector.restapi.org/
    └── <resource path>/
        └── GET|PUT|POST/
            ├── exec
            ├── result[.<extension>]
            └── result[.<extension>]_<session-id>
~~~

The endpoint leaf must:

- be named `GET`, `PUT`, or `POST`;
- contain an `exec` FIFO;
- contain at least one result FIFO; and
- reside below the configured domain entry.

Files in parent directories describe request arguments. A result FIFO extension
is mapped to an HTTP content type. For example, `result.json` becomes
`application/json`, while `result.svg` becomes `image/svg+xml`.

API providers also publish `*.md` files in the same tree. These files describe
the endpoints and act as change notifications for the REST API sidecar.

## Building the initial snapshot

The following flow runs when the sidecar starts and after every accepted
restart:

~~~mermaid
flowchart TD
    A["Wait for the domain directory in /api"] --> B["Clear restored_API"]
    B --> C["Traverse the filesystem API"]
    C --> D["Identify endpoint leaves by method and FIFO set"]
    D --> E["Restore JSON schemas"]
    C --> F["Collect Markdown files"]
    F --> G["Build combined index.md"]
    E --> H["Generate Flask query processors"]
    G --> H
    H --> I["Start the Flask server"]
    I --> J["Publish PID and hostname/port mapping"]
~~~

### 1. Wait for a provider

`watchdog_server.sh` waits for
`${SHARED_API_DIR}/${MAIN_SERVICE_NAME}`. The REST API cannot construct a
route table before at least one provider has published the domain.

### 2. Traverse the filesystem

`restore_api_from_pseudo_fs.py` calls
`gather_api_schemas_from_mount_point()`. The traversal is depth-first and
starts at the configured domain directory.

For every visited directory, the collector:

- records child directories so the logical query path can be reconstructed;
- reads argument definitions from that directory;
- collects `*.md` files; and
- inspects special files to find FIFOs.

A directory is treated as an endpoint when it has an `exec` FIFO and at least
one result FIFO. The collector then reconstructs:

- `Method` from the leaf directory name;
- `Query` from the path beginning at the configured domain;
- `Params` from argument definitions on the path; and
- `Content-Type` from the result FIFO extension.

### 3. Restore local schema files

Each discovered endpoint becomes a JSON file in
`/package/restored_API`. The watchdog clears this directory's generated
contents and rebuilds them for every snapshot, so removed filesystem endpoints
cannot survive in the next generated HTTP application.

The collected Markdown files are concatenated into
`restored_API/index.md`. When a Markdown heading matches a restored endpoint,
the restorer appends an HTTP `execute` link.

The watchdog requires at least one restored JSON schema and a generated
`index.md`. If either is missing after the configured retry limits, it treats
the filesystem API as incomplete and stops instead of serving a partial route
table.

## Generating HTTP query processors

The watchdog creates the runnable Flask module in two stages:

1. copy `cgi_template.py` to the generated `cgi.py`; and
2. append the output of `build_api_cgi.py`.

`build_api_cgi.py` reads every restored JSON schema and emits a Flask route
for its query path and method. Each generated processor maps HTTP activity back
to the FIFO protocol:

1. derive a stable client session from the HTTP method, REST API hostname, and
   remote hostname;
2. locate the endpoint's shared `exec` FIFO and result FIFO;
3. serialize accepted request parameters;
4. write one EOL-terminated request to `exec`;
5. wait for the session result FIFO; and
6. return its content using the schema's content type.

Normal GET, PUT, and POST processing uses `APIQuery`. HEAD processing uses
`APIQueryInterruptible` so opening, writing, result-pipe creation, and reading
all remain bounded by a timeout.

## HEAD keep-alive probes

Every generated endpoint also accepts HEAD. A HEAD processor sends:

~~~text
API_KEEP_ALIVE_CHECK=<tag> SESSION_ID=<session>
~~~

The filesystem API server returns the same tag through the session result FIFO.
The HTTP endpoint returns 200 only when the received tag matches. A send failure,
timeout, or mismatched tag returns 503.

HEAD is a complete FIFO transaction, not a metadata-only HTTP shortcut. It must
therefore be included in active-request accounting from before the `exec`
write until after the result is read.

The generated handler increments `queries_in_progress` before sending the
probe and decrements it in `finally`. This invariant holds for successful
responses, early 503 responses, and exceptions.

## Keeping the generated server synchronized

`init.sh` watches the shared filesystem API for Markdown create, delete, and
modify events. It groups bursts of events before scheduling a restart, because
several providers can publish their documentation during the same startup
window.

The script also compares the current Markdown-file count with the count from
the previous snapshot. This is a safeguard for changes that happened between
`inotifywait` observation windows.

When a change is detected:

1. `init.sh` removes the published server-address link so callers do not
   discover a server being replaced.
2. It repeatedly sends SIGINT to the current Flask PID.
3. The Flask signal handler checks `queries_in_progress`.
4. While any FIFO transaction is active, SIGINT is ignored.
5. After the last transaction finishes, a subsequent SIGINT terminates Flask.
6. The watchdog's `wait` returns and its outer loop starts another full
   discovery and generation cycle.
7. The new server publishes its PID and address only after it responds to an
   HTTP readiness probe.

~~~mermaid
sequenceDiagram
    participant Provider
    participant Init as init.sh
    participant Flask
    participant Watchdog
    participant FS as Filesystem API

    Provider->>FS: Publish or remove API Markdown
    FS-->>Init: inotify change
    Init->>Flask: SIGINT
    alt FIFO request is active
        Flask-->>Init: Ignore signal
        Init->>Flask: Retry SIGINT
    end
    Flask-->>Init: Exit after active requests reach zero
    Flask-->>Watchdog: wait returns
    Watchdog->>FS: Restore a new complete snapshot
    Watchdog->>Watchdog: Regenerate cgi.py
    Watchdog->>Flask: Start new instance
    Flask-->>Watchdog: HTTP readiness succeeds
~~~

This design keeps each running Flask instance internally consistent: it serves
one complete snapshot for its entire lifetime. Updates are applied by replacing
the process, not by mutating its route table while requests are executing.

## Restart-safety invariant

The critical invariant is:

> A generated HTTP processor must not be terminated after it writes a FIFO
> request but before it consumes that request's result.

Violating the invariant leaves the filesystem API's result producer blocked
without a reader. A later request using the same client session can then receive
the abandoned result, or can observe two results as one FIFO byte stream.

Before version 1 of this fix, HEAD returned before the common
`queries_in_progress` increment used by GET, PUT, and POST. The restart handler
therefore observed zero active queries and could terminate Flask during a HEAD
probe. Tracking the complete HEAD transaction closes that gap while preserving
the intended one-client/one-session FIFO model.

## Availability and failure behavior

- Discovery and startup have bounded retry counts. An incomplete filesystem
  snapshot causes the sidecar to stop rather than publish incomplete routes.
- FIFO HEAD operations have a 30-second transaction budget.
- During a snapshot replacement, the address link is absent and the old process
  is shutting down; callers should retry temporary connection failures.
- A restart waits for active requests. A permanently stuck request is bounded
  by its FIFO timeout so it cannot defer restart indefinitely.
- The watchdog always reconstructs `restored_API` and `cgi.py`; generated
  state is never treated as authoritative across restarts.

## Verification

The generator regression test verifies that:

- generated CGI is syntactically valid;
- HEAD increments `queries_in_progress` before FIFO execution;
- both `execute` and `wait_result` are inside the protected transaction; and
- `finally` always decrements the counter.

An end-to-end restart test should additionally trigger a Markdown update while
a HEAD result is pending, then verify that the HEAD succeeds, the restart occurs
afterward, and the next HEAD using the same session receives only its own tag.
