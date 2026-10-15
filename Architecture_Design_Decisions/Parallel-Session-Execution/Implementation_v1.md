# File-system API parallel session execution: implementation v1

## Scope

Version 1 changes the common CLI file-system API generator so an endpoint can
execute different sessions concurrently while preserving serial execution
within each session.

The issue was first noticed during rag_bulk_add development, but no bulk-RAG
behavior is implemented here. The reusable implementation is in
common/build_api_services.py and is enabled by an endpoint schema.

## Behavior before the change

The generated server combined three responsibilities in one synchronous loop:

- reading commands from exec;
- executing the endpoint command; and
- coordinating result publication.

The reader was a short-lived cat process. After it reached EOF, the server
iterated over the captured commands. It could not dispatch the next command
while the current executor was running, regardless of SESSION_ID.

~~~mermaid
sequenceDiagram
    autonumber
    participant CA as Client, session A
    participant CB as Client, session B
    participant F as exec FIFO
    participant R as Temporary cat reader
    participant S as Generated server loop
    participant E as Endpoint executor
    participant RA as Result FIFO, session A
    participant RB as Result FIFO, session B

    CA->>F: write request A
    CB->>F: write request B
    F->>R: read available command stream
    R-->>S: captured requests, then EOF
    Note over F,R: Reader closes between input cycles

    S->>E: execute request A
    activate E
    E-->>S: result A
    deactivate E
    S-->>RA: publish result A

    Note over CB,S: Session B waits behind unrelated session A
    S->>E: execute request B
    activate E
    E-->>S: result B
    deactivate E
    S-->>RB: publish result B

    S->>R: start a new FIFO reader
~~~

Consequences of this behavior:

- one slow session blocked every other session on the endpoint;
- SESSION_ID affected result naming but not execution concurrency; and
- recreating the request reader exposed a reader-lifecycle race to concurrent
  FIFO writers.

## Behavior after the change

An opted-in generated server separates dispatch from execution. The dispatcher
holds exec open and creates a background handler for every command. Each
handler depends only on the previous handler for the same SESSION_ID.

~~~mermaid
sequenceDiagram
    autonumber
    participant CA1 as Client A1, session A
    participant CB as Client B, session B
    participant CA2 as Client A2, session A
    participant F as exec FIFO
    participant D as Persistent dispatcher
    participant HA1 as Handler A1
    participant HB as Handler B
    participant HA2 as Handler A2
    participant EA as Executor A
    participant EB as Executor B
    participant RA as Result FIFO A
    participant RB as Result FIFO B

    Note over F,D: Read and keepalive descriptors remain open
    CA1->>F: request A1
    F->>D: read A1
    D->>HA1: start with no predecessor

    CB->>F: request B
    F->>D: read B
    D->>HB: start with no predecessor

    CA2->>F: request A2
    F->>D: read A2
    D->>HA2: start with predecessor A1
    HA2->>HA1: wait on A1 request state

    par Independent sessions execute concurrently
        HA1->>EA: execute A1
        EA-->>HA1: result A1
    and
        HB->>EB: execute B
        EB-->>HB: result B
        HB-->>RB: publish result B
    end

    alt Result A1 is consumed
        HA1-->>RA: publish result A1
    else Result A1 has no reader
        HA2->>RA: start temporary drain reader
        HA1-->>RA: unblock stale result writer
    end
    HA1-->>HA2: predecessor done
    HA2->>EA: execute A2
    EA-->>HA2: result A2
    HA2-->>RA: publish result A2
~~~

The diagram shows both invariants:

- A and B can overlap because their session chains are independent.
- A2 cannot execute before A1's executor and result-writer lifecycle are
  resolved.

## Schema contract

An endpoint enables the feature with:

~~~json
{
  "ParallelBySession": true
}
~~~

create_cli_server_content_from_schema() reads the property. Its default is
false, and any non-Boolean value raises a generation error.

generate_cli_server_content() receives parallel_by_session. The true branch
inserts the parallel helper functions and replaces the legacy request loop.
The false branch leaves the original template unchanged.

This is intentionally a CLI-server feature. GUI listener generation is not
changed.

## Generated dispatcher initialization

The parallel branch creates:

~~~bash
parallel_session_state_root=$(mktemp -d ...)
declare -A PARALLEL_REQUEST_STATE
PARALLEL_REQUEST_COUNTER=0
~~~

PARALLEL_REQUEST_STATE maps a SESSION_ID to its newest request-state directory.
The counter supports periodic pruning.

The dispatcher then opens the FIFO descriptors:

~~~bash
exec {PARALLEL_REQUEST_READ_FD}<"$pipe_request"
exec {PARALLEL_REQUEST_KEEPALIVE_FD}>"$pipe_request"
~~~

Opening the read descriptor waits for the first client writer. Once that
handshake completes, the private writer is opened. The private writer prevents
the read side from observing EOF during idle periods between external clients.

The dispatcher uses the same read descriptor for its lifetime:

~~~bash
while IFS= read -r -u "$PARALLEL_REQUEST_READ_FD" CMD_READ
do
    # Parse and dispatch one command.
done
~~~

The parallel output contains no cat-based request reader.

## Descriptor ownership

The dispatcher descriptors are inherited when Bash starts a background
function. parallel_session_request() immediately closes both inherited copies:

~~~bash
exec {PARALLEL_REQUEST_KEEPALIVE_FD}>&-
exec {PARALLEL_REQUEST_READ_FD}<&-
~~~

Closure happens before waiting for a predecessor or invoking an executor.
Executor processes and result-writer descendants therefore cannot inherit the
request FIFO ownership.

This prevents a critical false-availability state:

1. the dispatcher exits;
2. a handler remains alive;
3. the handler's inherited read descriptor keeps exec open;
4. a client successfully writes a new command; and
5. no dispatcher exists to consume it.

When the main loop exits, it closes its keepalive and read descriptors.

## Request dispatch

The original parsing and result-FIFO selection remain in the main loop. After
SESSION_ID and API_KEEP_ALIVE_CHECK are extracted, the parallel branch:

1. increments PARALLEL_REQUEST_COUNTER;
2. prunes finished state every 64 requests;
3. creates a new request-state directory;
4. reads the current session-map entry as previous_state;
5. replaces the map entry with the new state;
6. starts parallel_session_request() in the background;
7. stores the handler PID; and
8. immediately continues reading exec.

Advancing the map before starting another read ensures that two adjacent
requests for the same session form the correct predecessor chain.

## Request-state representation

Each request-state directory can contain:

| Entry | Writer | Consumer |
| --- | --- | --- |
| handler.pid | Dispatcher | Successors and diagnostic cleanup. |
| result_writer.pid | Handler | A same-session successor. |
| result_ready | Handler | A same-session successor. |
| done | Handler EXIT trap | Successors and pruning. |

The state directory is intentionally small. Request content and executor output
remain in their existing channels and shell variables.

parallel_remove_request_state() removes known entries and then removes the
directory if empty. parallel_prune_finished_requests() scans the session map,
removes completed state, and unsets its map entry.

## Handler lifecycle

parallel_session_request() receives:

- the complete command;
- the request number;
- SESSION_ID;
- a keepalive value, when applicable;
- the resolved session result FIFO;
- previous_state; and
- its own request_state.

It installs an EXIT trap that creates done, then calls
parallel_wait_for_previous_request().

After the predecessor is resolved, the handler either:

- returns the keepalive payload without invoking the endpoint; or
- runs the generated endpoint executor and Base64-encodes its stdout.

It logs START before execution and FINISH after execution.

## Same-session predecessor handling

parallel_wait_for_previous_request() returns immediately when previous_state is
empty or absent.

Otherwise it waits until the predecessor creates done. During the wait it
performs two recovery checks.

### Dead predecessor handler

If handler.pid exists but that process no longer exists, the function creates
done. This prevents a dead handler from blocking its session chain forever.

### Blocked predecessor result writer

If result_ready and result_writer.pid exist and the writer is alive, the
successor:

1. starts a temporary reader for the shared session result FIFO;
2. waits in bounded intervals for the writer to exit;
3. sends TERM if the writer remains alive;
4. waits again;
5. sends KILL if necessary; and
6. reaps the temporary reader.

This generalizes the existing result watchdog to background per-session
handlers. It ensures a client that abandons one result cannot permanently block
the next request for that same session.

Requests for other sessions do not inspect or wait for this state.

## Result publication

After the endpoint executor completes, the handler starts result publication in
a background process:

~~~text
decoded executor output -> session-specific result FIFO
~~~

The handler records result_writer.pid and creates result_ready before waiting
for the publisher. A successful publisher produces a CONSUMED log record. A
terminated or failed publisher produces RESET.

The handler does not create done until result publication exits. Thus a
same-session successor observes both execution and publication as one ordered
lifecycle.

## Legacy server preservation

The legacy template remains active when ParallelBySession is false. It retains:

- the nested request loop;
- the cat-based input cycle;
- synchronous endpoint execution; and
- its previous request-admission behavior.

This distinction is covered by generation and runtime tests. Parallel servers
must contain the persistent descriptors and must not contain cat $pipe_request.
Legacy servers must retain cat $pipe_request and must not contain the parallel
state helpers.

## Failure and shutdown behavior

- The dispatcher can continue accepting other sessions when one handler or
  executor fails.
- A handler's EXIT trap makes failure visible to its successor.
- A dead predecessor is converted to done by PID validation.
- A stale result writer is drained, then terminated with bounded escalation.
- Child handlers do not retain dispatcher FIFO descriptors.
- Normal dispatcher exit closes both persistent descriptors.
- A client racing with a real dispatcher exit may still receive EPIPE. The
  server architecture removes normal reader cycling but cannot make writes
  survive process death.

## Tests

common/images/unit_test/test_4_parallel_sessions.py provides seven regression
tests:

1. ParallelBySession is opt-in, and generated parallel and legacy servers have
   the expected structures.
2. The schema property must be Boolean.
3. Different sessions execute concurrently and receive only their own results.
4. Two bursts of 24 concurrent sessions are accepted across an idle interval.
5. Two requests with the same session do not overlap.
6. Repeated unread predecessors are drained before later same-session requests.
7. A non-opted-in endpoint keeps legacy serial admission behavior.

The tests inspect generated Bash as well as executing the generated services.
All seven pass. The generated parallel server also passes bash -n.

## Operational verification

For an opted-in endpoint:

- generated output should contain PARALLEL_REQUEST_READ_FD and
  PARALLEL_REQUEST_KEEPALIVE_FD;
- generated output should not contain cat $pipe_request;
- logs for different SESSION_ID values should show overlapping START-to-FINISH
  intervals;
- logs for the same SESSION_ID should remain ordered;
- an unread result followed by another same-session request should produce
  drain or RESET behavior rather than a permanent stall; and
- after dispatcher termination, no handler should retain an exec FIFO
  descriptor.

This version implements session ordering and dispatch concurrency. It does not
impose a global executor limit; an endpoint that needs such a limit should add
an independent admission policy without changing the per-session chain.
