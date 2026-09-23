# Issue 115: asynchronous file upload design review

This document reviews the file-upload extension proposed in
[issue 115](https://github.com/SergeyIvanov87/Code-Metric-Visualizer-Platform/issues/115)
and records the selected design. It is a design decision and implementation
guide, not an implementation itself.

## Relationship to the current pseudo-filesystem API

The current API already separates request initiation from result consumption. A
client writes a newline-terminated argument string to the long-lived `exec`
FIFO, while the generated CLI listener eventually publishes output through
`result[.<extension>]` or `result[.<extension>]_<SESSION_ID>`. The client does
not have to consume one result before initiating another request.

The upload proposal does not replace that asynchronous transaction model and
does not introduce an async path prefix. It extends selected queries with a
second input phase so a client can stream a file—or, in a future extension, a
directory representation—after ordinary request metadata has been accepted.
The improvement is primarily a better upload experience: large binary content
does not travel in the line-oriented `exec` argument string.

A query opts into this behavior through its generated executor. Existing
queries that do not invoke the deferred-query utilities keep their current
behavior and paths.

## Selected functional design

### Query parameter

Every participating query declares three ordinary schema parameters, each with a
query-specific default such as `5`:

* `WaitInitialQueryTimeoutSec` is the maximum silence period between publishing
  the ephemeral input FIFO and receiving the first bytes.
* `WaitQueryUpdateTimeoutSec` is the maximum silence period after at least one
  byte has arrived. Each successfully read chunk resets this timer. Its expiry
  commits the accumulated byte stream as complete input.
* `WaitResultConsumptionTimeoutSec` is the maximum period after processing has
  completed for a client to consume the final result FIFO. Its expiry releases
  blocked result-pipe participants and deletes the unique request directory.

Existing pseudo-filesystem generation creates all three parameter files, and the
existing argument machinery applies persistent values or per-request overrides
like any other query parameters. None of these values is a boolean async switch.
The generated executor's use of the common launcher defines the two-phase
contract.

### Per-query generated executor

Each participating microservice exposes its upload-capable query in
`api_generator.py`. Its generated executor invokes a common utility and supplies
the API directory, the microservice-specific processing executable, and the
resolved query arguments. The intended interface is:

```text
deferred_query_launcher.py \
  --api-directory "${api_directory}" \
  --processor "${processor_path}" \
  -- "${OVERRIDEN_CMD_ARGS[@]}"
```

The generated query implementation remains non-blocking: it runs only the
launcher, never the long-running processor. The `--` delimiter makes the
boundary between launcher options and query arguments explicit. Uploaded bytes
are never placed in argv; they travel through the ephemeral FIFO.

The processing executable may be implemented in Python, Rust, C++, or another
container-supported language. It is individual to the microservice and owns all
business processing and output, including business failure status. `File
uploaded successfully` is only an example of one successful result, not a
hard-coded transport response.

### Deferred-query utilities

Two shared utilities split short request allocation from long-running work:

* `deferred_query_launcher.py` validates resolved arguments, atomically creates
  a unique request directory and its `input` FIFO, starts a detached
  `deferred_query_executor`, waits for its readiness signal, prints the input
  FIFO path, and exits.
* `deferred_query_executor` is the standalone request owner. It reads bytes from
  `input`, enforces both upload-inactivity timeouts and result retention,
  launches the microservice processor as its child, publishes that child's
  output through `async_result`, handles service signals, and removes its
  request directory during shutdown.

The launcher starts the executor with an interface equivalent to:

```text
deferred_query_executor \
  --processor "${processor_path}" \
  --input "${unique_request_directory}/input" \
  --initial-timeout "${WaitInitialQueryTimeoutSec}" \
  --update-timeout "${WaitQueryUpdateTimeoutSec}" \
  --result-timeout "${WaitResultConsumptionTimeoutSec}" \
  --session-id "${SESSION_ID}" \
  -- "${OVERRIDEN_CMD_ARGS[@]}"
```

The executor derives its stable `async_result` output path from the unique
directory. It invokes the processor without a shell and passes the validated
argv vector unchanged.

Python is sufficient for the first implementation because its standard library
provides `os.mkfifo`, non-blocking descriptors, selectors, monotonic clocks,
signal handling, detached process sessions, and child-process supervision. Rust
or C++ can be considered later if measurements show that process count,
throughput, memory, or cleanup latency justify the additional build and
distribution complexity.

## Control flow

1. The client writes ordinary configuration and query arguments, including
   `SESSION_ID` and optional `WaitInitialQueryTimeoutSec` and
   `WaitQueryUpdateTimeoutSec` and `WaitResultConsumptionTimeoutSec` overrides,
   to the query's existing `exec` FIFO.
2. The generated listener resolves parameter-file values and request overrides,
   then invokes the query's generated executor as it does today.
3. The generated executor invokes `deferred_query_launcher.py` with the API
   directory, processing-executable path, and resolved argv.
4. Before allocating request artifacts, the launcher validates all three timeouts,
   `SESSION_ID`, executable path, and optional upload metadata. It returns an
   allocation error through `result..._<SESSION_ID>` if validation fails.
5. The launcher atomically creates a unique directory below the query directory.
   Its safe name includes an encoded `SESSION_ID` for troubleshooting plus a
   generated unique suffix. FIFO names inside it need not be unique: they are
   simply `input` and `async_result`.
6. The launcher creates `input` and starts `deferred_query_executor` in a new
   process session with the processor path, input path, initial timeout, update
   timeout, result-consumption timeout, session, and resolved argv. The executor
   is no longer the launcher's child after the launcher exits, so the generated
   API server never waits for the long-running request PID.
7. The deferred executor opens and initializes the input side and signals
   readiness through a private channel. Only after verifying readiness and that
   `input` is a FIFO does the launcher print its path and exit. The unmodified
   generated listener publishes that path through `result..._<SESSION_ID>`.
8. The client reads the ephemeral FIFO name and streams local bytes into it, for
   example:

   ```text
   cat /host/system/path/file > <ephemeral-input-fifo>
   ```

9. The deferred executor starts `WaitInitialQueryTimeoutSec` when the endpoint
   becomes ready. If no bytes arrive before it expires—including when a client
   reads the FIFO path and does nothing—the executor performs shutdown cleanup
   and exits without invoking the processor.
10. The first received bytes cancel the initial timer and start
    `WaitQueryUpdateTimeoutSec`. Every later chunk resets the update timer. EOF
    or one complete update-timeout interval without more bytes commits the
    accumulated stream as complete input. This inactivity framing allows writes
    larger than `PIPE_BUF` to arrive as multiple non-atomic chunks without the
    first chunk being mistaken for the entire upload.
11. The deferred executor runs the processing executable as its child and
    captures its actual output in a bounded temporary result inside the unique
    directory. This prevents the business processor from remaining blocked on
    a result FIFO that has no reader.
12. When processing completes, the executor begins publishing the captured
    output through `async_result` and starts
    `WaitResultConsumptionTimeoutSec`. Successful consumption is the normal end
    of the request: the executor removes the result data, both FIFOs, and the
    entire unique directory, then exits.
13. If the result-consumption timeout expires first, the executor performs
    bounded FIFO unblocking, terminates any result-delivery helper, deletes the
    unique directory, and exits. This is result-retention expiry, not a business
    processing failure.
14. During service shutdown, `api_management.py` signals all registered
    `deferred_query_executor` instances. Each executor stops and reaps its
    processor, closes descriptors, and removes its request directory before
    exiting; ordinary schema-directory cleanup then continues.

## Why the launcher must detach the deferred executor

The current generated CLI server invokes a query executor synchronously,
captures its stdout, and then publishes the captured value to
`result..._<SESSION_ID>`. The deferred-query utilities therefore cannot remain in
the foreground for the full upload and processing lifecycle. If it did, the
FIFO name would not reach the client until the upload operation had already
finished—an impossible handshake.

The two utilities consequently have distinct process lifetimes:

1. The short-lived **launcher** validates the request, creates its directory and
   input FIFO, starts the executor, waits for readiness, writes only the input
   FIFO path to stdout, and exits.
2. The standalone **deferred executor** receives the file, refreshes the idle
   timer, runs the microservice-specific executable as its own child, publishes
   the result, handles signals, and cleans up the unique directory.

One process cannot initially create an unrelated process: the executor begins as
a descendant of the launcher. The launcher can use a double-fork/`setsid`
sequence or an equivalent detached-process facility so the executor is
reparented and survives after the launcher exits. The API server must not wait
for that executor PID. The executor remains the direct parent of the business
processor and must reap it.

The detached executor must close or redirect every inherited stdout, stderr,
and pipe descriptor used by the generated server's command substitution.
Forking without closing those descriptors can keep command substitution waiting
for EOF after the launcher exits. This process and descriptor handoff is the
principal prototype required to validate the claim that common `build_api_*`
scripts need no changes.

The launcher registers the executor PID and request directory before publishing
readiness. `api_management.py` uses that registry (or another exact
process-identification mechanism) to signal live executors; it must not rely on
an imprecise process-name substring match.

## Established decisions and mitigations

### Existing paths and generators remain valid

There is no async prefix and no new request kind. A participating query uses its
existing path and declares one ordinary parameter. `build_api_pseudo_fs.py`,
`build_api_services.py`, and common parameter handling require no async-specific
branch. Query schemas, participating `api_generator.py` files, container
packaging of the common utility, and per-query processing executables do change.

### One unique directory identifies each deferred request

The launcher atomically creates a unique directory below the query directory.
Its name includes an encoded `SESSION_ID` for operator troubleshooting and an
independent generated suffix that guarantees uniqueness. Artifacts inside it use
stable names: `input` and `async_result`; they do not repeat `SESSION_ID` or the
unique suffix. Completion, timeout, or shutdown can remove the whole request
with one recursive directory cleanup.

### File bytes are streamed by the client

The client uses `cat file > FIFO`; it does not write a pathname with `echo` for
the server to dereference. This works across container path namespaces and
keeps binary data out of line-oriented shell argument parsing.

### The API directory is server-owned

Container user/group policy denies clients directory write access. Only the
service creates, replaces, and removes FIFO artifacts, while clients receive the
specific FIFO permissions needed to write upload content and read results. This
mitigates client-created artifact and path-substitution attacks.

### Validation happens before allocation

The launcher validates control metadata before creating the request directory,
FIFO, or deferred executor. Optional size or concurrency admission can be added
at this point, but spam protection and a worker pool are not required for the
first implementation. The allocation request remains a single small write no
larger than `PIPE_BUF`.

### Readiness gates publication

The launcher publishes no FIFO path until the deferred executor has opened the
launcher-created input FIFO, created the result FIFO, initialized its input
handling, signalled readiness, and passed an input-node type check. Executor exit
or readiness timeout returns allocation failure and removes the request
directory without advertising an unusable FIFO.

### Initial and update silence periods frame the upload

`WaitInitialQueryTimeoutSec` protects against a client that obtains an input
FIFO and never writes to it. Its expiry is cancellation and cleanup.
`WaitQueryUpdateTimeoutSec` starts after the first bytes and resets after every
later chunk. Its expiry means that the upload is complete, not failed. EOF also
completes the upload immediately.

The update timer intentionally provides message framing above FIFO chunking. A
payload larger than `PIPE_BUF` may arrive through many reads; processing begins
only after EOF or a full silent update interval, rather than after an arbitrary
read boundary. A sender must therefore keep gaps between intended chunks below
the configured update timeout.

A timer thread may implement this policy if read events reset a monotonic
deadline and completion is synchronized with EOF and signals. A selector/event
loop is also valid. Exactly one path may commit initial timeout, EOF, or update
timeout.

### The per-query executable owns the business result

The deferred executor transports the per-query executable's output unchanged;
it does not invent a universal upload-success response. The microservice
executable remains responsible for reporting its actual business outcome.

### Result retention is bounded and cleanup is part of normal completion

The executor captures processor output in a bounded temporary result before
delivering it through `async_result`. Once delivery starts,
`WaitResultConsumptionTimeoutSec` bounds how long the executor retains that
result for a consumer. Normal consumption and retention expiry both end with
the executor removing the FIFOs, temporary result, and entire unique directory.

On retention expiry, the executor uses bounded FIFO unblocking to release any
result reader or writer and terminates a remaining delivery helper. Expiry is a
transport-retention outcome and does not replace or rewrite the processor's
business result.

### Shutdown cleanup stays integrated

All artifacts remain in unique directories below the schema-defined query
directory. `api_management.py` first sends `SIGTERM` to each registered
`deferred_query_executor` and observes it finish its shutdown procedure,
then performs ordinary query-directory cleanup. Each executor intercepts
container termination, stops and reaps its processor child, closes descriptors,
and removes its own unique directory.

The executor's shutdown procedure may reuse the approach in
`api_management.py`: terminate the processor, perform bounded read/write
operations on `input` and `async_result` to release blocked producers or
consumers, close its own descriptors, and then unlink the FIFOs and directory.
The operations must be bounded so shutdown cannot block on an absent peer.
Signal handlers should only record or wake a shutdown request; process waits,
FIFO unblocking, and filesystem cleanup belong in normal control flow.

## Remaining limitations and decisions

### Session identity is not artifact identity

The unique request directory correlates `input` with `async_result`, so neither
FIFO name contains `SESSION_ID`. The session remains in the directory name only
for troubleshooting and in the existing initial `result..._<SESSION_ID>`
handshake. The session component is encoded before use in a directory name.
Because the initial handshake is still session-addressed, duplicate active
sessions must be rejected or serialized so the FIFO path cannot reach the wrong
client.

### Optional upload integrity contract

EOF or update-timeout silence completes the stream, but neither detects a client
that deliberately sends only a prefix. Queries that need stronger integrity may
declare a byte count or digest. The deferred executor verifies supplied values
before invoking business processing.

### Processing input contract

Each query must choose whether its executable receives a staged local pathname,
an inherited descriptor, or standard input. A staged file simplifies retries
and exact byte-count/digest validation but consumes storage. Streaming reduces
storage but couples executor speed and failure directly to FIFO ingestion.

## Lifecycle state model

```text
PREFLIGHT -> REJECTED
  -> REQUEST_DIRECTORY_CREATED
       -> INPUT_FIFO_CREATED
            -> DEFERRED_EXECUTOR_STARTING -> ALLOCATION_FAILED
                 -> EXECUTOR_READY
                      -> HANDSHAKE_PUBLISHED
                           -> WAITING_FOR_INITIAL_INPUT
                                -> INITIAL_TIMEOUT -> CANCELLED
                                -> FIRST_CHUNK
                                     -> WAITING_FOR_UPDATE
                                          -> CHUNK_READ -> WAITING_FOR_UPDATE
                                                           (update timer reset)
                                          -> UPDATE_TIMEOUT/EOF
                                               -> INPUT_COMPLETE
                                                    -> PROCESSOR_RUNNING
                                                         -> RESULT_CAPTURED
                                                              -> WAITING_FOR_RESULT_CONSUMER
                                                                   -> CONSUMED -> CLEANED
                                                                   -> RESULT_RETENTION_EXPIRED
                                                                        -> CLEANED
                           -> CANCELLED
```

The initial timer and first read must have one winner. After the first read, EOF,
the update timer, and the next chunk must also be serialized: a chunk cannot
reset the timer after update silence or EOF has committed `INPUT_COMPLETE`.
Result consumption and result-retention expiry likewise have one winner, and
either transition must perform the same idempotent directory cleanup.

## Decisions required before implementation

1. Which queries opt into the deferred-query utilities, and what default initial,
   update, and result-consumption periods does each declare?
2. Does each processing executable receive a staged pathname, descriptor, or
   standard input?
3. Which queries require declared length and/or digest validation?
4. Which container users/groups and FIFO modes grant handshake-read,
   input-write, and result-read access?
5. How are duplicate active `SESSION_ID` values rejected or serialized?
6. How does `api_management.py` identify registered executors, and how long does
   it wait after `SIGTERM` before escalating shutdown?
7. What maximum captured-result size is allowed before the processor is stopped
   or its output is rejected?
8. Are retries idempotent, and how long is any idempotency key retained?

## Minimum acceptance tests

Implementation should include automated tests for:

* queries that do not opt in retaining their current paths and behavior;
* `WaitInitialQueryTimeoutSec`, `WaitQueryUpdateTimeoutSec`, and
  `WaitResultConsumptionTimeoutSec` defaults and per-request overrides using
  existing parameter handling without changes to common `build_api_*` scripts;
* invalid timeout, session, executable path, and enabled admission checks being
  rejected before an ephemeral FIFO or deferred executor is created;
* unique request directories being created atomically and containing the stable
  `input` and `async_result` FIFO names;
* no FIFO path being published until both endpoints exist and the deferred
  executor has signalled readiness;
* deferred-executor startup failure and readiness timeout returning allocation
  failure and removing the unique directory without publishing an input path;
* a client obtaining the name and sending nothing, followed by idle-timeout
  cleanup;
* initial silence cancelling and cleaning a request without running the processor;
* the update deadline starting at the first chunk and resetting after every
  later chunk;
* a multi-chunk upload whose total duration exceeds the update timeout while
  every gap remains below it;
* update-timeout silence committing the bytes already received and launching the
  processor;
* first-byte arrival racing with initial timeout, and EOF/chunk arrival racing
  with update timeout, with exactly one terminal transition;
* binary data, embedded newlines, empty files, and payloads larger than
  `PIPE_BUF`;
* optional declared-length and digest success and mismatch behavior;
* executor success and business-error output being forwarded unchanged;
* non-zero exit, signal termination, oversized output, and long-running
  processing;
* `SESSION_ID` appearing only in the encoded unique-directory name and initial
  handshake, never in the stable FIFO names;
* duplicate active sessions never delivering a handshake to the wrong client;
* successful result consumption deleting the complete unique request directory;
* a client that never consumes the final result, followed by
  `WaitResultConsumptionTimeoutSec` expiry, bounded result-FIFO unblocking, and
  complete unique-directory deletion;
* service termination during allocation, upload, processing, and result
  delivery leaving no child processes or open descriptors;
* `api_management.py` signalling all registered deferred executors, waiting for
  their processor children to be reaped, and then removing remaining query
  artifacts;
* executor shutdown using bounded FIFO unblocking so absent peers cannot stall
  container termination;
* container permissions preventing clients from creating, replacing, or
  unlinking API artifacts while still allowing intended FIFO operations.
