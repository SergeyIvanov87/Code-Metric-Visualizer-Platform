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
queries that do not invoke the common upload processor keep their current
behavior and paths.

## Selected functional design

### Query parameter

Every participating query declares an ordinary schema parameter named
`AsyncWaitQueryTimeoutSec`, with a query-specific default such as `5`. Existing
pseudo-filesystem generation creates the corresponding parameter file, and the
existing argument machinery applies its persistent value or a per-request
override exactly like any other query parameter.

`AsyncWaitQueryTimeoutSec` is not a boolean switch and does not decide whether a
query is asynchronous. It defines the maximum **idle interval** while waiting
for input on the ephemeral FIFO. The generated executor's use of the common
upload processor is what defines the query's two-phase upload contract.

### Per-query generated executor

Each participating microservice exposes its upload-capable query in
`api_generator.py`. Its generated executor invokes a common utility and supplies
the API directory, the microservice-specific processing executable, and the
resolved query arguments. The intended interface is:

```text
async_query_processor_file_uploader.py \
  --api-directory "${api_directory}" \
  --processor "${processor_path}" \
  -- "${OVERRIDEN_CMD_ARGS[@]}"
```

The `--` delimiter makes the boundary between utility options and query
arguments explicit. The common processor invokes the per-query executable
without a shell and passes the validated argv vector unchanged. Uploaded bytes
are never placed in argv; they travel through the ephemeral FIFO.

The processing executable may be implemented in Python, Rust, C++, or another
container-supported language. It is individual to the microservice and owns all
business processing and output, including business failure status. `File
uploaded successfully` is only an example of one successful result, not a
hard-coded transport response.

### Common upload processor

`async_query_processor_file_uploader.py` is a shared common utility. It owns:

* validation of upload-control metadata;
* generation and lifecycle of ephemeral FIFO names;
* readiness coordination;
* idle-timeout and signal handling;
* invocation and reaping of the per-query processing executable;
* publication and cleanup of the final-result FIFO.

Python is sufficient for the first implementation because its standard library
provides `os.mkfifo`, non-blocking descriptors, selectors, monotonic clocks,
signal handling, and child-process supervision. Rust or C++ can be considered
later if measurements show that process count, throughput, memory, or cleanup
latency justify the additional build and distribution complexity.

## Control flow

1. The client writes ordinary configuration and query arguments, including
   `SESSION_ID` and optionally an `AsyncWaitQueryTimeoutSec` override, to the
   query's existing `exec` FIFO.
2. The generated listener resolves parameter-file values and request overrides,
   then invokes the query's generated executor as it does today.
3. The generated executor invokes the common upload processor with the API
   directory, processing-executable path, and resolved argv.
4. Before creating any ephemeral FIFO or child process, the common processor
   validates the timeout, `SESSION_ID`, executable path, and any optional upload
   metadata. It returns an allocation error through the ordinary
   `result..._<SESSION_ID>` channel if validation fails.
5. The common processor generates a unique safe FIFO identifier and starts a
   supervisor. The supervisor creates the ephemeral input FIFO and final-result
   FIFO, opens or initializes the input side, and signals readiness through a
   private control channel.
6. Only after verifying the ready input node is a FIFO does the allocator print
   its name and exit. The unmodified generated listener captures that value and
   publishes it through the ordinary `result..._<SESSION_ID>` FIFO.
7. The client reads the ephemeral FIFO name and streams local bytes into it, for
   example:

   ```text
   cat /host/system/path/file > <ephemeral-input-fifo>
   ```

8. The supervisor starts an idle timer when the ephemeral endpoint becomes
   ready. Every successfully read chunk resets the timer to the full
   `AsyncWaitQueryTimeoutSec` interval. If no chunk arrives during one complete
   interval—including when the client reads the FIFO name and then does
   nothing—the supervisor closes and removes the input FIFO, terminates and
   reaps the waiting input process, and cleans up the request.
9. EOF marks the end of the byte stream. After EOF, the upload idle timer no
   longer applies. The supervisor supplies the received input to the
   microservice-specific executable using the agreed staged-file, descriptor, or
   standard-input contract.
10. The supervisor publishes the processing executable's actual output through
    `async_query_result_<fifo-id>_<SESSION_ID>`. After the client consumes that
    output, it reaps the child and removes the ephemeral artifacts.
11. Service shutdown continues through `api_management.py`, which unblocks the
    schema-defined query pipes and removes the query directory. The common
    processor must also respond to termination by stopping and reaping its own
    children before exiting.

## Why the allocator must detach the supervisor

The current generated CLI server invokes a query executor synchronously,
captures its stdout, and then publishes the captured value to
`result..._<SESSION_ID>`. The common upload processor therefore cannot remain in
the foreground for the full upload and processing lifecycle. If it did, the
FIFO name would not reach the client until the upload operation had already
finished—an impossible handshake.

The utility consequently has two internal roles:

1. A short-lived **allocator** validates the request, waits for supervisor
   readiness, writes only the ephemeral input FIFO name to stdout, and exits.
2. A detached **supervisor** receives the file, refreshes the idle timer, runs
   the microservice-specific executable, publishes its result, and cleans up.

The supervisor must close or redirect every inherited stdout, stderr, and pipe
descriptor used by the generated server's command substitution. Forking without
closing those descriptors can keep command substitution waiting for EOF even
after the allocator exits. This descriptor handoff is the principal prototype
required to validate the claim that common `build_api_*` scripts need no
changes.

## Established decisions and mitigations

### Existing paths and generators remain valid

There is no async prefix and no new request kind. A participating query uses its
existing path and declares one ordinary parameter. `build_api_pseudo_fs.py`,
`build_api_services.py`, and common parameter handling require no async-specific
branch. Query schemas, participating `api_generator.py` files, container
packaging of the common utility, and per-query processing executables do change.

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

The common processor validates control metadata before creating FIFOs or
forking the supervisor. Optional size or concurrency admission can be added at
this point, but spam protection and a worker pool are not required for the first
implementation. The allocation request remains a single small write no larger
than `PIPE_BUF`.

### Readiness gates publication

The allocator publishes no FIFO name until the supervisor has created both
endpoints, initialized its input handling, signalled readiness, and passed an
input-node type check. Child exit or readiness timeout returns allocation
failure without advertising an unusable FIFO.

### Idle timeout protects against inactive and stalled uploaders

`AsyncWaitQueryTimeoutSec` is a silence interval, not an end-to-end deadline.
The timer begins when the input endpoint is ready and is recharged after every
chunk read from the FIFO. It therefore cleans up a client that obtains a FIFO
name and sends nothing, as well as a client that begins an upload and then
stalls. Continuous progress is allowed even when the total upload lasts longer
than one timeout interval.

A timer thread may implement this policy, provided chunk-read events reset a
monotonic deadline and timeout cleanup is synchronized with EOF and signal
handling. A selector/event-loop implementation is also valid and may avoid a
thread. Exactly one path must win the transition from waiting for input to
processing or timeout cleanup.

### The per-query executable owns the business result

The generic processor transports the per-query executable's output unchanged;
it does not invent a universal upload-success response. The microservice
executable remains responsible for reporting its actual business outcome.

### Shutdown cleanup stays integrated

All ephemeral artifacts remain inside the schema-defined query directory, so
`api_management.py` retains directory cleanup responsibility. The common
supervisor additionally owns termination and reaping of its live processing
child because unlinking FIFO names alone cannot stop a process holding an open
descriptor.

## Remaining limitations and decisions

### FIFO unlink is not process cancellation

Removing a FIFO pathname does not close descriptors already referring to it.
The supervisor must use non-blocking I/O plus `poll`/`select`, or explicitly
terminate and reap a blocked input child when the idle deadline expires. Cleanup
must close descriptors before removing names and remain idempotent when a chunk,
EOF, timeout, signal, and service shutdown race.

### Request correlation must be unambiguous

The generated FIFO identifier correlates the final result. `SESSION_ID` names
the initial result FIFO and remains user-selected context. Duplicate active
sessions must be rejected or serialized so a handshake cannot reach the wrong
client. Generated identifiers use a safe alphabet and atomic no-replace
creation; any session value embedded in a pathname is validated or encoded.

### Upload completion contract

EOF ends the stream, but detecting a client that deliberately sends only a
prefix requires an optional declared byte count or digest. Each participating
query must decide whether it needs those fields. When supplied, the supervisor
verifies them before invoking business processing.

### Result consumption has a separate lifetime

The upload idle timeout ends at EOF and must not terminate business processing.
A client that never consumes the final result can keep the supervisor blocked on
the output FIFO. The implementation must choose a separate result-delivery
limit or an administrative cleanup policy; expiry of delivery must remain
distinguishable from the processing executable's business result.

### Processing input contract

Each query must choose whether its executable receives a staged local pathname,
an inherited descriptor, or standard input. A staged file simplifies retries
and exact byte-count/digest validation but consumes storage. Streaming reduces
storage but couples executor speed and failure directly to FIFO ingestion.

## Lifecycle state model

```text
PREFLIGHT -> REJECTED
  -> SUPERVISOR_STARTING -> ALLOCATION_FAILED
       -> ENDPOINT_READY
            -> HANDSHAKE_PUBLISHED
                 -> WAITING_FOR_INPUT
                      -> CHUNK_READ -> WAITING_FOR_INPUT  (idle timer reset)
                      -> INPUT_IDLE_TIMED_OUT
                      -> INPUT_COMPLETE
                           -> RUNNING
                                -> RESULT_READY -> CONSUMED
                                                 -> RESULT_EXPIRED
                      -> CANCELLED
```

The transition out of `WAITING_FOR_INPUT` must have a single winner. In
particular, a timer callback must not remove the FIFO after EOF has committed
`INPUT_COMPLETE`.

## Decisions required before implementation

1. Which queries opt into the common upload processor, and what default idle
   timeout does each declare?
2. Does each processing executable receive a staged pathname, descriptor, or
   standard input?
3. Which queries require declared length and/or digest validation?
4. Which container users/groups and FIFO modes grant handshake-read,
   input-write, and result-read access?
5. How are duplicate active `SESSION_ID` values rejected or serialized?
6. What independent limit or cleanup policy applies to unconsumed final results?
7. Are retries idempotent, and how long is any idempotency key retained?

## Minimum acceptance tests

Implementation should include automated tests for:

* queries that do not opt in retaining their current paths and behavior;
* `AsyncWaitQueryTimeoutSec` defaults and per-request overrides using existing
  parameter handling without changes to common `build_api_*` scripts;
* invalid timeout, session, executable path, and enabled admission checks being
  rejected before an ephemeral FIFO or supervisor is created;
* no FIFO name being published until both endpoints exist and the supervisor has
  signalled readiness;
* supervisor startup failure and readiness timeout returning allocation failure
  without publishing an ephemeral name;
* a client obtaining the name and sending nothing, followed by idle-timeout
  cleanup;
* the idle deadline resetting after every chunk;
* a multi-chunk upload whose total duration exceeds the timeout while every gap
  remains below it;
* a partial upload whose next chunk never arrives;
* EOF racing with idle timeout, with exactly one terminal transition;
* binary data, embedded newlines, empty files, and payloads larger than
  `PIPE_BUF`;
* optional declared-length and digest success and mismatch behavior;
* executor success and business-error output being forwarded unchanged;
* non-zero exit, signal termination, oversized output, and long-running
  processing;
* duplicate active sessions never delivering a handshake to the wrong client;
* a client that never consumes the final result;
* service termination during allocation, upload, processing, and result
  delivery leaving no child processes or open descriptors;
* `api_management.py` removing input/result FIFOs and the query directory;
* container permissions preventing clients from creating, replacing, or
  unlinking API artifacts while still allowing intended FIFO operations.
