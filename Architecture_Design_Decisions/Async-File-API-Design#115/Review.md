# Issue 115: asynchronous file API design review

This note reviews the control flow proposed in
[issue 115](https://github.com/SergeyIvanov87/Code-Metric-Visualizer-Platform/issues/115)
against the current pseudo-filesystem API. It is a design review, not an
implementation specification.

## What the current API guarantees

For every legacy operation, the CLI service owns one long-lived `exec` FIFO and
one long-lived default `result[.<extension>]` FIFO. A request is a
newline-terminated argument string written to `exec`. The listener executes
requests serially, but publishes each result from a background process so it can
return to reading `exec` without waiting for a result consumer.

`SESSION_ID` selects a per-session result FIFO named
`result[.<extension>]_<SESSION_ID>`. It does not create a separate request FIFO,
worker, queue, or durable transaction. Before reusing a session, the listener's
watchdog drains an unread previous result so that the previous background writer
cannot block the next request forever. Consequently, the present API has
"latest request" rather than durable queue semantics.

The Python client also treats asynchronous I/O differently from asynchronous
job execution: `APIQueryInterruptible` bounds how long a client waits while
opening, writing, or reading a FIFO. It does not cause the server to defer the
operation.

## Reading the proposed flow

The async API is a new, standalone query family. An async path prefix is placed
between the query path and its `GET`, `POST`, or `PUT` component. For example,
if the prefix is named `async`, the two APIs are separate endpoints:

```text
/api/<query>/POST/exec        # existing synchronous query
/api/<query>/async/POST/exec  # new async-only query
```

`async` is illustrative; the schema must define the final reserved component.
The async endpoint does not change or overload the result contract of the
legacy endpoint.

The proposal introduces a two-stage exchange:

1. Write metadata, including `SESSION_ID` and `ASYNC_WAIT_TIMEOUT`, to the
   operation's existing `exec` FIFO.
2. Read a newly allocated upload FIFO name from a session-specific handshake
   result.
3. Stream the file contents to that FIFO before its acceptance deadline (for
   example, `cat /host/system/path/file > <input-fifo>`).
4. Run the operation after input has arrived.
5. Read the operation result from a second, job-specific FIFO.

This is a useful separation of **job allocation**, **input transfer**, and
**result retrieval**. A dedicated input FIFO also avoids holding the shared
`exec` FIFO open for a potentially large payload. However, the issue's process
flow and naming rules do not yet define a safe protocol.

## Established decisions and mitigations

Review discussion resolved several questions from the original proposal. These
are design constraints, not remaining objections:

### Standalone async endpoint

The async API is generated under its own reserved path prefix. It does not
replace a legacy endpoint and does not need an `ASYNC=1` discriminator. The
prefix must be represented in the API schema so generators, help, discovery,
and `api_management.py` all recognize the endpoint. Legacy paths and services
remain unchanged.

### File bytes are streamed by the client

The intended operation is `cat /host/system/path/file > pipe_QSENTR445S`. The
shell opens the client's local file and sends its bytes; the server never opens
a client-supplied pathname. The `echo` example in the issue should therefore be
corrected. Binary payloads must bypass line-oriented argument parsing and shell
variables.

### The API directory is server-owned

Container user/group policy denies clients write access to the `GET`, `POST`, or
`PUT` directory. Only the service creates, replaces, and removes FIFO artifacts;
clients can only use the permitted FIFO endpoints. This mitigates client-created
artifact and path-substitution attacks. Tests should verify both the configured
directory permissions and the expected client read/write capabilities.

### Metadata and optional admission are checked before forking

The primary `server_api_listener` validates all metadata read from `exec` before
creating an ephemeral FIFO or forking a watchdog. Invalid metadata is returned
through the initial session result and never enters the ephemeral lifecycle.

If resource admission is introduced, the same pre-fork stage can reject an
excessive input size, timeout, or active-request count. A worker pool is not
required, and spam protection can be deferred. Finite numeric values should
still be validated so one accepted request cannot accidentally request
unbounded resources. The small allocation record should be emitted as one write
no larger than `PIPE_BUF`.

### Shutdown cleanup uses `api_management.py`

Ephemeral artifacts are reaped by the existing `api_management.py` shutdown
path rather than a second cleanup subsystem. The async endpoint must be present
in the schemas consumed by that manager. Its directory and pipe naming must
allow `remove_api_fs_pipes_node` to unblock the standard handshake result and
remove the endpoint directory, including its input and async-result FIFOs.

### Listener readiness gates the handshake response

The watchdog generates a unique FIFO name and passes it to the new
`async_server_listener`. The async listener creates the ephemeral input FIFO
and the final-result FIFO, opens or initializes everything it needs for input,
and signals readiness to its watchdog through a private control channel. The
watchdog verifies that the input node is a FIFO before reporting its name
through the initial `result_<SESSION_ID>` handshake.

The client therefore cannot observe the name before the async listener has
started and the endpoint is usable. If the child exits or the readiness wait
times out, the watchdog reports allocation failure instead of publishing the
ephemeral FIFO name. Server-owned directory permissions prevent a client from
substituting a node during this exchange.

### The query executor owns the business result

The Python or Bash query executor is responsible for the actual processing and
for producing its business result, including any processing failure status.
The async listener forwards that output to the final-result FIFO. The phrase
`File uploaded successfully` in the issue is only an example of one successful
executor outcome; it is not a fixed transport-level response.

## Remaining challenges and limitations

### 1. Unlinking a FIFO is not cancellation

Removing a FIFO pathname after `ASYNC_WAIT_TIMEOUT` does not close file
descriptors that already refer to it. A listener can therefore remain blocked
after the name disappears. Opening a FIFO for reading in blocking mode can also
prevent the listener from observing a deadline.

The listener must use non-blocking I/O plus `poll`/`select`, or the watchdog must
retain the child PID and terminate and reap it on expiry. Timeout must use a
monotonic clock. Cleanup closes descriptors before removing names and must be
idempotent when timeout, input arrival, and cancellation race.

### 2. The upload-completion boundary is underspecified

The issue says the timeout stops applying after the listener has read the data.
A streamed file can arrive partially and then stall, and EOF does not prove that
a disconnected client sent the entire intended file.

The protocol should define completion using a declared byte count and,
optionally, a digest. It must also decide whether `ASYNC_WAIT_TIMEOUT` is an
absolute upload deadline or an idle timeout. Missing, non-numeric, negative, or
unsupported values are rejected during preflight.

### 3. The generated FIFO identifier must correlate the result

The unique identifier generated for the input FIFO can also correlate the final
result. `SESSION_ID` is user-selected context and names the allocation handshake
FIFO. A user should choose a unique session when allocations may overlap; the
service must reject or serialize a duplicate active session so a handshake
cannot reach the wrong client.

A final result name can contain both values, for example
`async_query_result_<fifo-id>_<SESSION_ID>`, or only the FIFO identifier when no
session is supplied. Generated identifiers use a safe alphabet and atomic
no-replace creation. Any `SESSION_ID` embedded in a pathname is validated or
encoded, and shell pathname expansions remain quoted.

### 4. Result delivery can outlive input acceptance

The async listener intentionally remains alive until the user consumes the
result, and the watchdog waits for it. `ASYNC_WAIT_TIMEOUT` stops applying once
input is accepted, so a client that never reads the final result can otherwise
retain both processes and the result FIFO forever.

The protocol needs a separate result-delivery timeout or an administrative
cleanup rule. Expiry may discard an unconsumed result, but it must remain
distinguishable from executor failure.

## Recommended control flow

The smallest safe extension that preserves the proposed FIFO model is:

1. The client writes one small allocation request to the standalone async
   endpoint's `exec` FIFO, including `SESSION_ID`, a bounded
   `ASYNC_WAIT_TIMEOUT`, and optional declared input length and digest.
2. The async endpoint listener validates all metadata and any enabled resource
   limits. On failure it reports rejection through the initial handshake result;
   it creates no ephemeral FIFO and forks no watchdog. On success it starts a
   watchdog with the validated configuration and operation executor path.
3. The watchdog generates the unique FIFO name, starts the async listener with
   that name, and waits on a private readiness channel. The listener creates the
   input and final-result FIFOs and signals readiness after initialization. The
   watchdog verifies the input FIFO and only then publishes its name through
   `result_<SESSION_ID>`. A child exit or readiness timeout produces allocation
   failure without advertising the FIFO.
4. The client opens the input FIFO and streams exactly the declared number of
   bytes. The reader rejects extra bytes, incomplete input, and a digest
   mismatch. The acceptance deadline remains active until validation completes.
5. Once input is accepted, the watchdog closes and unlinks the input FIFO,
   moves the job from `WAITING_FOR_INPUT` to `RUNNING`, and the listener invokes
   the existing operation executor with the staged file path plus the original
   validated arguments.
6. The listener writes the query executor's actual output—including its
   business success or failure status—to
   `async_query_result_<fifo-id>_<SESSION_ID>`. It exits after the client consumes
   the result; the watchdog reaps it and removes the ephemeral nodes.
7. If input does not complete before `ASYNC_WAIT_TIMEOUT`, the watchdog
   terminates and reaps the listener and removes both FIFOs. After input is
   accepted, a separate result-delivery policy governs abandoned output.
8. Per-request cancellation goes through the watchdog, which closes descriptors,
   terminates and reaps its child, and performs idempotent cleanup. Service
   shutdown continues through `api_management.py`, which unblocks the endpoint
   pipes and removes the async endpoint directory with its ephemeral artifacts.

Suggested states are:

```text
PREFLIGHT -> REJECTED
  -> WATCHDOG_STARTING
       -> LISTENER_STARTING -> ALLOCATION_FAILED
            -> ENDPOINT_READY
                 -> HANDSHAKE_PUBLISHED
                      -> WAITING_FOR_INPUT
                           -> RUNNING -> RESULT_READY -> CONSUMED
                                                    -> RESULT_EXPIRED
                           -> INPUT_TIMED_OUT
                           -> CANCELLED
```

Every transition to `RUNNING` or a terminal state must be single-winner and
atomic from the client's perspective.

## Decisions required before implementation

1. What is the reserved async path-prefix name and how is an async-only query
   represented in the JSON schema?
2. Which input-size, result-size, timeout, and concurrency bounds belong in the
   initial validation? Admission/spam protection may be deferred independently.
3. Does the executor receive a staged local pathname, standard input, or both?
4. Which container users/groups and FIFO modes grant each client its required
   handshake-read, input-write, and result-read access?
5. Are retries expected to be idempotent, and for how long is an idempotency key
   remembered?
6. Is `ASYNC_WAIT_TIMEOUT` an absolute upload deadline or an idle upload
   timeout, and what separate limit applies while waiting for result consumption?

## Minimum acceptance tests

Implementation should not be considered complete without automated tests for:

* legacy queries remaining byte-for-byte compatible and generated under their
  original paths;
* async queries being generated only under the reserved path prefix;
* duplicate active `SESSION_ID` allocations being rejected or serialized as
  specified, with no handshake delivered to the wrong client;
* separate allocations receiving different generated FIFO identifiers and
  result paths;
* the handshake name not being published until the async listener has created
  both FIFOs and signalled readiness;
* listener startup failure and readiness timeout returning allocation failure
  without publishing an ephemeral FIFO name;
* binary data, embedded newlines, empty files, and inputs larger than
  `PIPE_BUF`;
* client disconnect before open, midway through upload, and after upload;
* input arriving exactly at the timeout boundary;
* invalid timeout, length, digest, session ID, and enabled resource-limit checks
  being rejected before any ephemeral FIFO or watchdog is created;
* executor success and business-error output being forwarded unchanged, plus
  non-zero exit, signal termination, oversized output, and long-running execution;
* a client that never consumes or acknowledges a result;
* cancellation racing with input completion and execution completion;
* `api_management.py` shutdown cleanup in every non-terminal state, including
  removal of the input FIFO, async-result FIFO, and endpoint directory;
* container permissions preventing clients from creating, replacing, or
  unlinking API artifacts while still allowing the intended FIFO operations;
* cleanup leaving no child processes, open descriptors, or orphaned nodes.
