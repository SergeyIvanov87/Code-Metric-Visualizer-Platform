# Issue 122: bulk directory ingestion design review

This document reviews the directory-ingestion proposal in
[issue 122](https://github.com/SergeyIvanov87/Code-Metric-Visualizer-Platform/issues/122)
and proposes an implementation that reuses the deferred-query lifecycle added
for streaming file uploads. It is a design decision and implementation plan,
not the implementation itself.

## Executive decision

Add `POST +/streaming_directory_upload` to `utility/file-uploader`. The query
allocates a request-scoped **staging directory** and one **status FIFO per
worker**, returns them in the deferred-query readiness report, ingests closed
files into an existing persistent destination with a bounded worker pool, and
returns one final JSON result through the executor-owned `async_result` FIFO.

Reuse `common/deferred_query_launcher.py` unchanged and retain the existing
`common/deferred_query_executor.py` lifecycle. The executor receives two small,
backward-compatible enhancements: pass resolved query arguments to channel
preparation, and bound/publish the final result as one `PIPE_BUF`-sized atomic
FIFO record.
The new processor follows the same three-mode contract as
`streaming_file_upload_processor.py`:

1. `--check-arguments` validates the request before allocation;
2. `--prepare-api-channel` creates and reports processor-owned channels; and
3. normal execution owns ingestion while the deferred executor supervises it,
   bounds its final stdout, publishes the final result, and cleans the request.

This design deliberately does **not** send progress on processor stdout.
Processor stdout is already reserved for the bounded final result captured by
the deferred executor. Live progress and heartbeats use processor-owned
`status-<id>` FIFOs advertised in the extensible readiness report.

The issue's “zero-copy” wording is not adopted. Reading from `tmpfs` into a
bounded userspace buffer and writing it to the nested upload FIFO is a copy. The
useful guarantee is instead **bounded userspace memory and prompt source-space
reclamation**, independent of the total dataset size.

## Task breakdown

### 1. API and generated executor

* Add `utility/file-uploader/API/streaming_directory_upload.json`.
* Extend `utility/file-uploader/api_generator.py` with a second executor that
  invokes `deferred_query_launcher.py` exactly as the existing file query does,
  changing only the processor path.
* Keep the existing pseudo-filesystem request, handshake, session, and result
  paths. No new common generator behavior or async URL prefix is required.
* Extend the existing streaming-file schema and processor with optional
  `expected_bytes`; existing callers that leave it empty retain current
  behavior.

### 2. Directory-ingestion processor

Add `utility/file-uploader/streaming_directory_upload_processor.py`. It owns:

* request validation and channel preparation;
* recursive filesystem observation and reconciliation;
* safe relative-path reconstruction;
* bounded scheduling and worker concurrency;
* invoking the existing `streaming_file_upload` pseudo-filesystem API once per
  accepted file, streaming source bytes into the returned input FIFO, consuming
  its result, and deleting the source only after API-confirmed success;
* per-worker JSON progress/heartbeat FIFOs; and
* final aggregate result generation.

Upload behavior remains out of the common deferred executor, just as file
upload behavior does in implementation v1.

### 3. Container and deployment wiring

* Package the new schema and processor through the existing Dockerfile globs.
* Add the selected recursive filesystem observer dependency to the image. The
  preferred implementation is Python `watchdog`, using `on_closed`,
  `on_moved`, directory-create, and deletion events. The already installed
  `inotify-tools` remains useful for diagnosis but must not be parsed as a
  filename protocol because arbitrary Unix filenames can contain separators
  and newlines.
* Mount a shared tmpfs-backed staging root at the same absolute path (proposed
  `/dev/shm/file-uploader`) in the service and client containers. Channel
  preparation creates the real staging directory there and an `input` symbolic
  link inside the API request directory. This needs no `CAP_SYS_ADMIN`: the
  mount is configured by the container runtime, not created by the service.
  The single-file query already keeps payload bytes out of API arguments and
  streams them directly to destination storage; it does not need a second
  payload staging directory.
* Keep persistent output on `/uploads` by default; deployments may override it
  with another mounted directory.

### 4. Tests and operations

* Add processor, launcher, generated API, race, and shutdown tests alongside
  the current file-uploader functional suite.
* Extend the post-Compose artifact check to cover directory-upload request
  directories and FIFOs.
* Add a documented client example that obtains the JSON handshake, copies a
  tree into `input`, closes/renames each file into place, consumes `status`, and
  then consumes `result`.

## Reuse of the streaming-file implementation

### Components reused and minimally extended

`deferred_query_launcher.py` already provides everything needed for allocation:

* validation of the three lifecycle timeouts and `SESSION_ID`;
* processor preflight before filesystem allocation;
* duplicate-active-session rejection;
* atomic request-directory creation;
* detached executor startup and readiness timeout;
* an extensible JSON readiness report; and
* publication through the existing session-specific result FIFO.

`deferred_query_executor.py` already provides everything needed after
allocation:

* processor-driven input-channel preparation;
* executor-owned `async_result` creation;
* lifecycle ownership independent of the generated API listener;
* signal forwarding and bounded child termination;
* bounded final-result capture;
* bounded final-result retention; and
* whole-request and session-lock cleanup.

The executor intentionally remains unaware of directories, inotify, workers,
progress messages, and destination persistence. Its channel-preparation command
is extended from:

```text
processor --request-directory <request> --prepare-api-channel
```

to:

```text
processor --request-directory <request> --prepare-api-channel -- <resolved query arguments>
```

The current single-file processor already accepts trailing arguments in this
mode and can ignore them, so its behavior does not change. The directory
processor uses `workers` to create every `status-<id>` FIFO before readiness.

The executor also queries `_PC_PIPE_BUF` from `async_result`, rejects processor
output larger than that runtime limit, and publishes the complete final JSON in
one write. This replaces the fixed 1-MiB capture limit with the platform's
atomic FIFO-record limit for both upload queries.

### Existing extension points used

The v1 handshake requires `input`, `input_type`, `result`, and `result_type`,
but permits additional fields. The directory processor returns:

```json
{
  "input": "/api/.../deferred-.../input",
  "input_type": "DIRECTORY",
  "status": [
    "/api/.../deferred-.../status-1",
    "/api/.../deferred-.../status-2",
    "/api/.../deferred-.../status-3",
    "/api/.../deferred-.../status-4"
  ],
  "status_type": "FIFO[]",
  "protocol": "cmvp.directory-upload.v1"
}
```

The executor adds:

```json
{
  "result": "/api/.../deferred-.../async_result",
  "result_type": "FIFO"
}
```

This is the intended use of the transport-neutral v1 report. The launcher only
applies FIFO checks to its required `input` and `result` fields today, so its
code does not change. The processor must therefore perform strict post-creation
checks on the staging-directory link and every status FIFO. A later hardening change
may teach the launcher to validate all typed report fields and containment, but
that is not a prerequisite for issue 122 and should be made as a separate,
backward-compatible common-infrastructure change.

### Mandatory reuse through the streaming-file API

The pool does not import, execute, or otherwise call
`streaming_file_upload_processor.py`, `deferred_query_launcher.py`, or
`deferred_query_executor.py` for an individual file. Each pool worker acts only
as a client of the already generated `streaming_file_upload` pseudo-filesystem
API:

1. write one request to `streaming_file_upload/POST/exec`;
2. read its session-specific handshake result;
3. stream the staged source file into the returned `input` channel;
4. read the returned `result` channel; and
5. accept the file only when that API reports success and matching
   `received_bytes`.

This makes validation, timeout handling, destination-side temporary files,
`fsync`, non-overwriting installation, business-result formatting, and
per-request cleanup the responsibility of the existing API implementation. The
directory processor owns only discovery, filtering, scheduling, progress, and
aggregation.

One backward-compatible streaming-file API enhancement is required for safe
composition: add optional `expected_bytes` (empty by default). When present,
`streaming_file_upload_processor.py` verifies the received byte count before
installing its temporary file. A mismatch returns an error and removes the
temporary file. Every directory worker supplies the stable source size. This
prevents worker cancellation or a broken FIFO writer from publishing a valid
but truncated destination file. The directory pool still reaches this behavior
only through the public streaming-file API.

For parent `SESSION_ID=P` and one-based worker ID `N`, every nested request uses
`SESSION_ID=P.worker-N`. A worker processes only one file at a time, fully
consumes the nested result, and then reuses that same derived session for its
next file. If cleanup is still releasing the prior session, the worker observes
duplicate-session rejection through the API and retries with bounded backoff;
it never reads or manipulates the streaming query's internal session lock.
Different workers therefore run concurrently under distinct sessions while
preserving parent and worker correlation. Preflight limits `P` so the derived
value still satisfies the existing safe-character and 128-character
constraints. If an unrelated direct API client owns a derived session beyond
the bounded retry period, that worker reports failure rather than reading or
writing the unrelated request's channels.

The directory processor locates the sibling generated API node through its
configured shared API root and canonical service/query components; it does not
construct an executable path. For every file, a worker performs the same public
sequence available to an external client:

```text
write SESSION_ID=<P.worker-N>, destination=<target-parent>,
      preferred_filename=<basename>, expected_bytes=<source-size>, and metadata
      to .../streaming_file_upload/POST/exec
read .../streaming_file_upload/POST/result.json_<P.worker-N>
parse its input/result channel report
stream the source bytes to input
read and validate result
```

All argument values use the existing API request encoding rather than shell
evaluation. The worker validates that every returned channel is contained in
the sibling streaming-file query directory and has its declared type before it
opens the channel. A nested response is never accepted merely because its path
was present in JSON.

## Proposed query contract

The schema uses these ordinary parameters:

| Parameter | Default | Meaning |
| --- | --- | --- |
| `metadata` | `{}` | User JSON object echoed in the final result. |
| `destination` | `/uploads` | Existing persistent root inside the container. |
| `preferred_directory` | `""` | Optional base name below `destination`; an empty value generates `uploaded.<UTC timestamp>`. |
| `workers` | `4` | Fixed ingestion worker count, restricted to `1..32`. |
| `file_regex` | `.*` | Regular expression matched against each slash-separated relative file path; only matching files are copied. |
| `conflict_policy` | `fail` | V1 supports only non-overwriting installation; the explicit value leaves room for future policies. |
| `StatusHeartbeatIntervalSec` | `1` | Maximum interval between status records from an active worker. |
| `WaitInitialQueryTimeoutSec` | `60` | Maximum wait for the first accepted filesystem activity. |
| `WaitQueryUpdateTimeoutSec` | `5` | Quiet period after activity which commits an empty staging tree as complete. |
| `WaitResultConsumptionTimeoutSec` | `60` | Existing final-result retention period. |
| `SESSION_ID` | `default` | Existing deferred-request correlation and duplicate lock. |

For this query, `SESSION_ID` must also leave room for `.worker-<id>` within the
streaming-file API's 128-character session limit. With the v1 maximum of 32
workers, the parent is therefore limited to 118 safe characters. The exact
derived ID is visible in nested API artifacts and logs for correlation.

`destination/preferred_directory` is the ingestion root. All paths placed in
`input` are reproduced relative to that root. `preferred_directory` must be a
base name, not an absolute or multi-component path. The final root must not
exist at preflight. Because the existing channel-preparation call intentionally
does not receive business arguments, this check can race after the handshake.
Normal processor startup atomically creates the final destination root; a lost
race is returned as a business conflict before any input is deleted. V1 never
overwrites an existing file, directory, or symlink.

`file_regex` is compiled during preflight and applied with full-match semantics
to the normalized relative path, never an absolute host or container path. The
default `.*` accepts every regular file. Invalid expressions and expressions
over the configured pattern-length limit are rejected before allocation. A
closed file that does not match is counted as skipped and removed from staging
without being created below the destination. Destination directories are
created lazily only when they contain a matching file, and a bottom-up sweep
removes every zero-file directory after its files were filtered out. Therefore
a directory whose entire subtree is excluded by `file_regex` is absent from the
published destination. A skipped file does not contribute to copied/failed file
or byte totals; it contributes to the separate `files_skipped` counter.

Each worker owns an independent status FIFO exposed as `status-<id>`, where
`<id>` is the decimal worker ID from `1` through `workers`. The directory
processor creates these FIFOs directly during channel preparation and lists
their paths in the readiness report. No status symlink, per-worker subprocess,
or change to the streaming-file processor is necessary: status describes the
directory worker that is driving nested API calls, not an internal process of
the streaming-file implementation.

The status protocol is UTF-8 JSON Lines. Every record contains exactly the
worker ID as a JSON number, normalized relative path, bytes copied so far,
source file size, and status. `status` is one of `in progress`, `done`, or
`failed`. Example records from `status-2` are:

```json
{"worker_id":2,"path":"src/main.py","bytes":65536,"total_bytes":184321,"status":"in progress"}
{"worker_id":2,"path":"src/main.py","bytes":131072,"total_bytes":184321,"status":"in progress"}
{"worker_id":2,"path":"src/main.py","bytes":184321,"total_bytes":184321,"status":"done"}
```

Paths in events are slash-separated paths relative to the staging root. Error
records use the same five fields and the last successfully copied byte count;
detailed error descriptions remain in the final result. A worker emits `done`
only after the nested streaming-file API returns success with matching
`received_bytes`, making the
record both a completion notification and the signal that the individual file
is ready. While copying, it emits `in progress` after chunks as needed so no
active worker is silent longer than `StatusHeartbeatIntervalSec`. Thus each
`status-<id>` is both a progress stream and an external heartbeat channel.

Each JSON line, including its newline, must be no larger than the runtime
`_PC_PIPE_BUF` for that FIFO and is written with one `write` call. Because each
FIFO has exactly one worker writer, records remain ordered and atomic. The FIFO
persists for the request and may describe several files processed sequentially
by that worker. It closes when the worker terminates; completion of the whole
request is authoritative in `async_result`, not a magic `EOF_ALL_DONE` record.

The final `async_result` is one JSON object using the existing business-result
shape:

```json
{
  "error_code": "0",
  "error_description": "",
  "metadata": {},
  "path": "/uploads/uploaded.20260926T120000.000Z",
  "files_completed": "12/12",
  "directories_completed": "4/4",
  "bytes_completed": 105321,
  "files_failed": "0/12",
  "files_failed_path": [],
  "files_skipped": 3
}
```

The progress fields are strings in `completed/total` form. During ingestion,
the denominator is the number discovered so far and can increase; in the final
result it is fixed. The denominator of `files_completed` and `files_failed` is
the same total number of regular files accepted by `file_regex`.
`directories_completed` uses the total number of discovered directories.
`files_failed_path` contains every failed file's normalized relative path, in
lexical order, and is empty on success. `files_skipped` is the number of closed
regular files excluded by `file_regex`. Admission limits must account for all
failed paths and reject further input before the final JSON could exceed the
runtime `_PC_PIPE_BUF` limit of `async_result`; the list is never silently
truncated.

Progress is operational output: external consumers use it as a worker heartbeat
and as notification that an individual file is ready. Failure to attach a
status reader must nevertheless not stop ingestion or fill unbounded memory.
Workers open and write their FIFO non-blockingly; they may coalesce intermediate
`in progress` records under backpressure, but retain the latest progress and
make a bounded attempt to deliver `done` or `failed`. The final result remains
the authoritative request summary.

## Control flow

1. The client writes parameters and a unique `SESSION_ID` to the new query's
   existing `exec` FIFO.
2. The generated executor invokes `deferred_query_launcher.py`, supplying the
   query directory and the new processor.
3. Launcher preflight invokes the processor's `--check-arguments` mode. The
   processor validates JSON, worker bounds, `file_regex`, conflict policy,
   destination existence/writability, preferred base name, and destination-root
   conflict. Validation creates no request artifacts.
4. The launcher takes the existing session lock, allocates the unique request
   directory below the API tree, and starts the existing detached executor. The
   API directory contains no payload data.
5. The executor invokes `--prepare-api-channel` with the resolved query
   arguments. The processor validates the canonical request directory and the
   pre-mounted shared `/dev/shm/file-uploader` root, creates the real mode
   `02770` staging directory below that tmpfs root, and places an `input`
   symlink in the request directory. The absolute symlink target is valid in
   every participant because the shared tmpfs is mounted at the same path. It
   also creates one mode `0660` `status-<id>` FIFO per worker, verifies every
   node type and path containment, and returns its channel report. No runtime
   mount or `CAP_SYS_ADMIN` is required.
6. The executor creates `async_result`, adds it to the report, and returns the
   report to the launcher. The launcher publishes it through the existing
   `result.json_<SESSION_ID>` handshake and exits.
7. In parallel with publication, the executor starts the normal processor. The
   processor atomically creates the public destination root, starts the
   observer, performs an initial recursive reconciliation scan, then accepts
   work. The scan closes the
   readiness-to-observer race: entries copied after channel creation but before
   watcher startup are not lost.
8. The client opens the reported `status-<id>` FIFOs and copies files,
   directories, and nested directory trees into the reported `input` directory.
   A file becomes eligible only after a close-write event, a move into the tree,
   or a reconciliation scan establishes a stable candidate. Destination
   directories are created lazily for matching files; zero-file directories
   produced only by filtering are pruned.
9. The dispatcher normalizes the relative path, rejects unsafe node types, and
   evaluates `file_regex`. It deletes and reports a closed nonmatching file;
   otherwise it inserts a deduplicated task into a bounded `queue.Queue`. It
   never submits an unbounded number of futures.
10. A fixed worker creates the file's destination parent directory, derives
    `<parent SESSION_ID>.worker-<id>`, and invokes only the existing
    `streaming_file_upload` API. Its request supplies the derived session,
    destination parent, relative-path basename as `preferred_filename`, parent
    metadata, and nested lifecycle timeouts. It does not execute the
    streaming-file processor or deferred utilities directly.
11. The observer resets the update deadline for every accepted create, close,
    move, or deletion event. Periodic reconciliation discovers events missed
    through startup races or inotify queue overflow.
12. After reading the nested API handshake, the worker opens its returned input
    FIFO, reads the tmpfs source in bounded chunks, writes those chunks to the
    FIFO, and reports byte progress and periodic heartbeats to `status-<id>`.
    It then immediately consumes the nested API result. Matching
    `received_bytes` and `error_code == "0"` produce `done` and permit source
    deletion; allocation, transport, business-result, or byte-count failure
    produces `failed` and retains the source until parent-request cleanup.
13. Before the first accepted activity, initial-timeout expiry cancels the
    request without committing a destination tree. After activity, completion
    requires all of: the update quiet period elapsed, the task queue is empty,
    no worker is active, reconciliation finds no regular files, and all pending
    terminal worker status records have received their bounded delivery attempt.
14. On completion, the processor prunes zero-file destination directories,
    `fsync`s the destination root, closes every worker FIFO, prunes the tmpfs
    staging tree, and writes only the final JSON object to stdout.
15. The executor verifies that object fits the runtime atomic pipe limit,
    publishes it with one write through `async_result`, and applies
    `WaitResultConsumptionTimeoutSec`. Consumption, retention expiry,
    cancellation, or shutdown removes the complete request directory, removes
    any remaining tmpfs request directory, and releases the existing session
    lock.

## Completion semantics

Issue 122 proposes “empty and idle” completion. That is retained, but made
precise. An empty staging tree alone is never completion: it is also the normal
state immediately after allocation and between bursts. `WaitInitialQueryTimeoutSec`
protects the first state, and `WaitQueryUpdateTimeoutSec` is the producer's
maximum allowed inter-burst silence after activity.

This has the same fundamental trade-off as update-silence framing for a byte
stream: a producer that pauses longer than the configured update period has
ended the request. Clients that cannot bound their pauses must construct the
tree elsewhere and rename completed entries into staging promptly, or select a
larger timeout.

V1 does not add an explicit completion marker because the requested contract is
idle-driven and the existing timeout parameters already express it. A future
protocol version may add a request-scoped seal operation for producers that
need an unambiguous completion barrier.

## Filesystem correctness and safety

### Path containment

Every event path is converted to a path relative to the canonical staging
directory. Reject absolute paths, `..`, NULs, and any path whose resolved parent
escapes the staging root. Perform destination operations relative to opened
directory descriptors where practical. Never trust a path merely because it
came from the observer.

V1 accepts regular files and directories only. It rejects symlinks, hard-linked
files (`st_nlink != 1`), sockets, devices, and FIFOs. Open source files with
`O_NOFOLLOW`; compare `fstat` identity with the queued identity before copying.
This prevents a client from using the privileged service to read or replace a
path outside either root.

### Durability and atomicity

A source file is deleted only after all of these succeed:

1. the source identity and size still match the eligible closed file;
2. all bytes were written to the nested API's returned input FIFO;
3. the nested final result has `error_code == "0"`;
4. its `received_bytes` equals both the worker's sent count and the stable source
   size; and
5. the worker fully consumed the nested result.

The final destination root is created atomically before workers accept input.
The existing streaming-file API writes its destination-side temporary file,
performs `fsync`, installs the individual file without overwrite, and reports
the final path. The directory worker does not duplicate any of those operations.
A `done` status therefore means the final path is already durable and visible
to an external consumer; it never means merely that FIFO transmission ended.

This deliberately chooses per-file atomic visibility over request-level atomic
rollback, matching issue 122's immediate file-ready notification and source
reclamation requirements. If a later file fails, earlier `done` files remain
available and are listed in the final partial-failure result. The processor
removes empty directories it created, but never removes a successfully
installed file during rollback or shutdown.

### Resource bounds and backpressure

Memory is bounded by `workers * 64 KiB`, queue metadata, path-state metadata,
and one fixed pending-status slot per worker; it is not proportional to file
contents. It can still grow with the number of path names unless admission bounds are defined.
V1 therefore sets limits for maximum relative-path bytes, depth, files,
directories, and total observed bytes. Crossing a limit stops acceptance and
returns a business error.

A bounded task queue applies backpressure to reconciliation. The event callback
must remain short and may mark a rescan-needed flag rather than block the
watchdog dispatcher. Inotify overflow also sets that flag. Reconciliation is
the source of truth; notifications are latency hints.

### Status FIFO behavior

Each worker is the sole writer of its own `status-<id>` FIFO and writes complete
JSON records no larger than that FIFO's `_PC_PIPE_BUF`. It opens and writes
non-blockingly, tolerates a late or absent reader, and cannot delay persistence
or processor shutdown. At most the latest `in progress` record is retained per
worker, so slow consumers cause progress coalescing rather than unbounded
queuing. The worker makes a bounded delivery attempt for `done` or `failed`;
aggregate counters and failure details remain available in the final result.

## Failure and shutdown behavior

* A per-file failure stops new scheduling, lets in-flight workers reach a safe
  boundary, emits `failed`, and returns a nonzero business result. No source is
  deleted before its own durable installation.
* Parent cancellation closes each active nested input writer and consumes the
  nested result for a bounded period. Because `expected_bytes` is mandatory for
  nested calls, a partial stream cannot be installed as success. Nested initial,
  update, and result timeouts provide a bounded fallback; service shutdown still
  lets `api_management.py` terminate all deferred requests in both queries.
* Observer startup failure and inotify watch exhaustion are business failures,
  not silent fallback. Inotify queue overflow triggers reconciliation; repeated
  overflow that prevents convergence fails the request.
* Processor `SIGTERM` stops observation and scheduling, wakes the monitor,
  cancels pending tasks, joins workers for a bounded period, lets each nested
  streaming-file request clean its own temporary file, removes empty destination
  directories and its tmpfs staging directory, closes all status FIFOs, and
  exits. Successfully installed files remain available. Signal handlers only
  set/wake a stop condition.
* The existing executor terminates and reaps the directory processor, removes
  the parent request directory, and releases its session lock. Existing
  `api_management.py` executor discovery and shutdown ordering also covers the
  nested streaming-file requests and is reused unchanged.
* A host still writing beneath `input` during cancellation may receive normal
  filesystem errors when cleanup removes the request. The client owns retry
  policy; v1 does not claim idempotency.

## Lifecycle state model

```text
PREFLIGHT -> REJECTED
  -> REQUEST_ALLOCATED
       -> CHANNELS_PREPARED
            -> HANDSHAKE_PUBLISHED
                 -> OBSERVER_STARTING -> FAILED
                      -> RECONCILING
                           -> WAITING_FOR_INITIAL_ACTIVITY
                                -> INITIAL_TIMEOUT -> CANCELLED
                                -> ACTIVITY
                                     -> ACCEPTING
                                          -> FILE_READY -> QUEUED
                                               -> NESTED_API_ALLOCATED
                                                    -> STREAMING -> RESULT_VALIDATED
                                                         -> SOURCE_REMOVED
                                                    -> FAILED
                                          -> UPDATE_QUIET
                                               -> RECONCILE
                                                    -> WORK_REMAINS -> ACCEPTING
                                                    -> QUEUE_EMPTY + NO_ACTIVE_WORK
                                                         -> DESTINATION_ROOT_SYNCED
                                                              -> WORKER_STATUSES_CLOSED
                                                                   -> RESULT_CAPTURED
                                                                        -> RESULT_CONSUMED
                                                                             -> CLEANED
                                                                        -> RESULT_EXPIRED
                                                                             -> CLEANED
                 -> SERVICE_STOP -> CANCELLED -> CLEANED
```

Only the monitor may transition from accepting work to request completion. It checks
the quiet deadline, dispatcher generation, queue unfinished count, active-worker
count, reconciliation result, and stop flag under one synchronization policy.
An event racing the quiet deadline either increments the generation before the
commit snapshot and is processed, or arrives after watcher shutdown and is
rejected by the closing staging directory.

## Rejected alternatives

### Call the streaming-file processor or deferred launcher directly

Rejected because it duplicates the generated API's argument resolution,
handshake, timeout, result, session-lock, and cleanup contract inside the pool.
Workers are ordinary clients of `streaming_file_upload/POST/exec` and its
returned channels. The only supported per-file integration boundary is that
pseudo-filesystem API.

### Put directory logic in `deferred_query_executor.py`

Rejected because it would couple common request lifetime infrastructure to
inotify, path validation, worker pools, and persistence policy. The v1 upload
implementation explicitly moved input-channel selection and consumption into
the business processor; issue 122 should preserve that boundary.

### Encode a tar archive through the existing file-upload FIFO

This maximizes literal code reuse but does not satisfy immediate per-file
reclamation or live per-file progress. It also introduces archive traversal,
link, ownership, and decompression concerns. It remains a useful separate API
for clients that cannot share a staging filesystem.

### Multiplex every worker onto one `status` FIFO

Rejected because consumers cannot independently monitor a worker, a slow
reader couples every worker's observability, and worker identity becomes only a
payload convention. One `status-<id>` FIFO per worker gives each heartbeat an
independent ordered channel. Nonblocking writes and `_PC_PIPE_BUF`-bounded JSON
records prevent an absent reader from blocking ingestion.

### Treat inotify as a complete event log

Rejected because watches are installed asynchronously, queues can overflow,
and recursive watching has directory-creation races. Initial and periodic
reconciliation are necessary for correctness.

### Hide the whole tree until request completion

Rejected because `done` must notify an external consumer that the individual
file is ready, and issue 122 requires immediate source reclamation and per-file
availability. V1 installs each file atomically in the public destination root.
Its final result explicitly describes partial failure instead of rolling back
files that were already reported ready.

## Implementation sequence

1. Add schema and generated executor; assert generated paths and parameters.
2. Implement processor argument validation and channel preparation; test node
   types, modes, containment, and readiness report fields.
3. Add `expected_bytes` to the existing streaming-file API and prove unchanged
   behavior when omitted plus rejection/cleanup on mismatch.
4. Implement safe reconciliation and a single worker as a pseudo-filesystem API
   client; test nested directories, filtering/pruning, binary/large files,
   conflicts, derived-session reuse, and unsafe nodes.
5. Add recursive observation, deduplication, bounded queue, and the remaining
   API-client workers; test files arriving before watcher startup, during
   streaming, and by rename.
6. Add per-worker status FIFOs, progress heartbeats, and the completion monitor;
   test absent/slow readers, atomic records, burst gaps, initial timeout, update
   quiet period, and races.
7. Add public destination creation, directory pruning, and partial-failure
   aggregation; inject nested allocation, input, business-result, byte-count,
   observer, and limit failures.
8. Exercise both generated pseudo-filesystem APIs under Compose and verify
   shutdown during initial wait, active copying, quiet detection, result wait,
   and a disconnected writer leaves no processes or request artifacts.

## Minimum acceptance tests

Implementation is complete only when automated coverage includes:

* the existing `streaming_file_upload` query retaining its API behavior after
  resolved arguments are added to channel preparation and the final result is
  limited to one atomic FIFO record;
* streaming-file `expected_bytes` omitted, matched, empty-file, mismatched, and
  interrupted-writer behavior, with mismatch never installing a destination;
* the new query using the existing launcher/executor lifecycle and returning
  its input link, `workers` status FIFO paths, channel types, result, and
  protocol version;
* invalid metadata, destination, preferred directory, worker count,
  `file_regex`, conflict policy, timeout, and duplicate session rejection before
  request allocation;
* a real staging directory on the pre-mounted shared tmpfs, an API-directory
  `input` symlink that resolves identically in service and client containers,
  direct per-worker status FIFOs, result FIFO types, permissions,
  containment, uniqueness, and cleanup without `CAP_SYS_ADMIN`;
* a producer copying before observer startup, incremental close-write, atomic
  move-in, dynamically created nested directories, empty directories, and
  reconciliation after simulated inotify overflow;
* arbitrary safe filenames including spaces and newlines, with JSON escaping;
* the default `.*` copying all regular files, selective relative-path matching,
  nested-path full-match behavior, excluded-file deletion, accurate
  `files_skipped`, and pruning directories whose files were all filtered out;
* rejection of traversal, symlinks, hard links, FIFOs, sockets, devices, and
  source identity changes while queued or copied;
* binary files, empty files, files larger than `PIPE_BUF`, many small files,
  total input larger than available process memory, and worker concurrency;
* every worker invoking only `streaming_file_upload/POST/exec` and returned
  channels, with tests that fail if it executes/imports the streaming processor,
  launcher, or executor directly;
* derived sessions exactly `<parent>.worker-<id>`, concurrent distinct worker
  sessions, sequential reuse by one worker, bounded duplicate-session retry,
  maximum parent-session length, and collision with an unrelated API client;
* destination non-overwrite behavior inherited through the nested API, source
  deletion only after successful result and matching `received_bytes`, `done`
  only after the public file is ready, and preservation/reporting of earlier
  successful files after an injected later failure;
* initial silence cancellation, activity-reset update timing, bursts whose
  total duration exceeds the update timeout, and no premature completion while
  work is queued or active;
* a first event racing initial timeout and a new event racing final quiet
  detection, each with exactly one valid transition;
* one `status-<id>` FIFO per worker, numeric stable request-local `worker_id`,
  the exact five-field schema, all three status values, chunk byte progress,
  heartbeat timing, file-ready `done`, records no larger than `_PC_PIPE_BUF`, a
  late reader, no reader, slow reader, per-worker coalescing, and FIFO EOF;
* final success/error JSON, completed/total ratios, and the lexically ordered
  complete `files_failed_path` array and `files_skipped` count delivered
  unchanged through `async_result`, plus rejection before the final result can
  exceed runtime `_PC_PIPE_BUF`, one-write publication, and result-retention
  expiry;
* admission-limit, observer-startup, queue-overflow, nested allocation/input/
  result failure, expected-byte mismatch, and nested result timeout producing
  bounded errors and an accurate partial result; and
* service termination in every lifecycle phase reaping the processor and
  workers and leaving no tmpfs staging directory, FIFO, session lock,
  incomplete temporary destination file, or deferred executor.

## Decisions fixed by this review

1. The feature is a new file-uploader query, not a new service and not a mode
   added to the single-file query.
2. The common launcher, API management, and API generators require no
   behavioral changes. The executor only passes resolved arguments to channel
   preparation and enforces atomic final-result publication.
3. The processor chooses a tmpfs directory input transport and one FIFO
   progress/heartbeat transport per worker through the extensible readiness
   report.
4. Processor stdout contains exactly one `_PC_PIPE_BUF`-bounded final result;
   each worker has a separate JSON Lines heartbeat and file-ready stream.
5. Completion uses initial and update inactivity timeouts plus a fully drained,
   reconciled system. Empty staging alone is insufficient.
6. Pool workers never call streaming-file implementation executables; each file
   is transferred exclusively through the existing pseudo-filesystem API using
   `<parent SESSION_ID>.worker-<id>`.
7. Source deletion follows nested API success plus exact `expected_bytes` and
   `received_bytes` agreement.
8. Every completed file becomes visible atomically before its worker emits
   `done`; request failure does not roll back files already reported ready.
9. Inotify accelerates discovery; reconciliation establishes correctness.
10. Payload staging resides on a shared `/dev/shm` mount and is linked from the
   API request directory; the container runtime supplies the mount without
   granting the service `CAP_SYS_ADMIN`.

## Follow-up decisions before coding

The implementation PR should choose and record concrete defaults for maximum
path length, depth, file count, directory count, total bytes, task-queue size,
heartbeat interval bounds, reconciliation interval, and bounded worker shutdown. It
should also decide whether the functional Compose environment can reliably
provision a shareable tmpfs-backed volume in CI; if not, correctness tests may
use a normal volume while a Linux-only mount test verifies the deployment
recipe separately.
