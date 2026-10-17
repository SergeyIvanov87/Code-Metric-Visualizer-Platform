# File-system API parallel session execution: architecture review

## Status

Accepted and implemented in version 1.

## Incidental discovery

The problem was discovered incidentally while adding concurrent file processing
to rag_bulk_add. That workload submitted several independent requests to the
rag_add file-system API, each with a different SESSION_ID, but only one
rag_add executor process ran at a time.

The bulk client was not the serialization point. Its concurrent callers exposed
a generic limitation in the generated file-system API server: one server
serialized every request for an endpoint, even when the requests belonged to
unrelated sessions.

The bulk endpoint is therefore only the discovery context. The defect and the
solution belong to the common file-system API service generator.

## Original file-system API behavior

A generated CLI server owned one request FIFO named exec and one base result
FIFO. Clients wrote newline-delimited commands to exec. A command normally
included SESSION_ID, and the server created or reused a result FIFO derived
from that value.

The request loop used a short-lived cat process to read the exec FIFO into a
here-string. It then handled the collected commands synchronously:

1. parse the next command;
2. resolve its SESSION_ID and result FIFO;
3. execute the endpoint command and wait for completion;
4. start a background writer for the result FIFO;
5. remember that writer for the existing watchdog; and
6. move to the next command.

This design had endpoint-wide serialization. SESSION_ID selected a result
channel and watchdog entry, but it did not define an execution concurrency
boundary. A long request for session A delayed a request for session B even
though the two requests did not share state.

## Root causes

### Synchronous dispatch

The main request reader also executed the request command. It could not return
to exec and dispatch another command until the current executor exited.

The generated service therefore behaved as one global session coordinator
rather than one coordinator per SESSION_ID.

### Implicit same-session lifecycle

The existing watchdog handled an unread result only when the main serial loop
eventually reached another request. Moving execution into uncoordinated
background processes would bypass that ordering and could allow two requests
with the same SESSION_ID to compete for the same result FIFO.

Parallelization therefore required more than appending an ampersand to the
executor command. It required explicit per-session dependency tracking.

### Unstable request-FIFO reader

The cat-based reader was recreated for each input cycle. Server startup cleanup
could also create a temporary FIFO reader and later terminate it.

Under concurrent admission, a client could successfully open exec while a
reader existed and then receive EPIPE if that reader disappeared before the
client's write. This was observed as one BrokenPipeError in a burst of
otherwise successful requests. The failed session had no server START record,
confirming that the request never reached its executor.

## Required semantics

The generic file-system API needed the following contract:

1. Requests with different SESSION_ID values may execute concurrently.
2. Requests with the same SESSION_ID execute strictly in arrival order.
3. A successor for a session must not start until its predecessor has finished
   execution and its result-publication lifecycle has been resolved.
4. If a predecessor is blocked writing an unread result, the existing watchdog
   behavior must drain or terminate that stale writer.
5. The request FIFO must have a stable reader for the lifetime of a parallel
   dispatcher.
6. Background handlers must not keep that reader alive after the dispatcher
   exits.
7. Existing endpoints must retain legacy serial admission unless their schema
   explicitly opts into the new behavior.

## Options considered

### Keep endpoint-wide serialization

This preserved behavior but prevented independent sessions from using available
CPU and downstream capacity concurrently. It was rejected.

### Start every request in the background

This enabled concurrency but removed same-session ordering. Two requests could
use the same result FIFO simultaneously or allow a newer result to overtake an
older unread result. It was rejected.

### Maintain one permanent coordinator process per session

This made ownership explicit but introduced a process registry, idle lifetime,
queue transport, crash recovery, and coordinator cleanup. It was more machinery
than the required ordering justified.

### Use a global executor pool

A pool could limit total processes but would still need per-session queues and
result-writer coordination. Global execution limits are a separate policy from
the session-ordering defect and can be added independently.

### Retry EPIPE only in clients

A bounded retry can protect against real service restarts, but it does not fix
endpoint-wide serialization or the unstable normal reader lifecycle. It was
retained as possible defense in depth, not selected as the architectural fix.

### Enable parallel dispatch for every generated endpoint

Holding exec open changes admission behavior. A legacy serial endpoint that is
busy can reject or delay admission today; a persistent reader permits the
kernel to buffer additional request records. Applying the change globally
would therefore be incompatible.

## Decision

Add the Boolean schema property ParallelBySession. When true, the common CLI
server generator emits:

- a persistent request dispatcher;
- one request-state directory per accepted request;
- an associative map from SESSION_ID to the latest request state;
- a background handler for each accepted request;
- a per-session predecessor wait;
- stale result-writer draining and bounded termination;
- periodic cleanup of finished state; and
- explicit closure of dispatcher FIFO descriptors in every child handler.

The dispatcher is free to accept the next command immediately after creating
its handler. Handlers for different sessions have no dependency and may execute
at the same time. A handler for the same session receives the previous state
and waits for it before invoking the endpoint executor.

Schemas without ParallelBySession, or with it set to false, continue to use the
legacy generated loop. Non-Boolean values are rejected during generation.

## Persistent FIFO decision

The parallel dispatcher holds two descriptors:

- a read descriptor used for every request; and
- a private write descriptor that prevents EOF when no external writer is
  connected.

Separate descriptors were chosen instead of opening the FIFO read-write. This
avoids relying on Linux-specific FIFO O_RDWR behavior.

The background handler closes both inherited descriptors immediately. The
dispatcher is consequently the only long-lived owner. When it exits, clients
cannot be misled by a child process that still has the FIFO open but cannot
dispatch requests.

## Per-session state decision

Each accepted request gets a temporary state directory. The server records:

| State entry | Purpose |
| --- | --- |
| handler.pid | Detect whether the predecessor handler still exists. |
| result_writer.pid | Identify a publisher blocked on the session result FIFO. |
| result_ready | Show that execution finished and result publication began. |
| done | Show that the handler exited. |

The session map points to the newest state. On dispatch, the old map entry is
passed to the new handler as its predecessor, and the map is advanced to the
new state immediately. This creates an ordered chain for each session without
blocking dispatch for other sessions.

## Consequences

### Benefits

- Concurrency is aligned with SESSION_ID rather than with the entire endpoint.
- Same-session result routing and watchdog semantics remain deterministic.
- The main dispatcher is no longer occupied by endpoint execution.
- The parallel request FIFO retains one reader during normal server operation.
- The feature is reusable by any generated CLI file-system API endpoint.
- Legacy endpoint behavior remains the default.

### Costs and limitations

- Every accepted parallel request creates a background handler and temporary
  state.
- The implementation periodically scans session state for cleanup.
- The feature controls ordering, not a global maximum executor count.
- Requests remain newline-delimited FIFO records and retain the protocol's
  existing atomic-write assumptions.
- A genuine dispatcher exit can still produce EPIPE for a writer racing with
  shutdown.
- Generated Bash relies on Bash associative arrays and dynamic descriptors.

## Validation

The common unit suite verifies:

- explicit schema opt-in and Boolean validation;
- overlapping execution for different sessions;
- strict serialization for the same session;
- correct result routing by session;
- draining multiple successive unread same-session results;
- unchanged legacy serial admission;
- presence and ownership of persistent request descriptors;
- removal of the cat-based request reader only from parallel servers; and
- two bursts of 24 concurrent sessions separated by an idle interval.

All seven parallel-session tests pass. The generated server also passes Bash
syntax validation.

