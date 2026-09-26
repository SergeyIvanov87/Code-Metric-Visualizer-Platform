# Issue 122: bulk directory ingestion design review

This document reviews the directory-ingestion proposal in
[issue 122](https://github.com/SergeyIvanov87/Code-Metric-Visualizer-Platform/issues/122)
and proposes an implementation that reuses the deferred-query lifecycle added
for streaming file uploads. It is a design decision and implementation plan,
not the implementation itself.

## Executive decision

Add `POST +/streaming_directory_upload` to `utility/file-uploader`. The query
allocates a request-scoped **staging directory** and a **status FIFO**, returns
both in the existing deferred-query readiness report, ingests closed files into
an existing persistent destination with a bounded worker pool, and returns one
final JSON result through the executor-owned `async_result` FIFO.

Reuse `common/deferred_query_launcher.py` and
`common/deferred_query_executor.py` unchanged for the first implementation.
The new processor follows the same three-mode contract as
`streaming_file_upload_processor.py`:

1. `--check-arguments` validates the request before allocation;
2. `--prepare-api-channel` creates and reports processor-owned channels; and
3. normal execution owns ingestion while the deferred executor supervises it,
   bounds its final stdout, publishes the final result, and cleans the request.

This design deliberately does **not** send progress on processor stdout.
Processor stdout is already reserved for the bounded final result captured by
the deferred executor. Live progress uses an additional processor-owned FIFO
advertised in the extensible readiness report.

The issue's “zero-copy” wording is not adopted. Reading from `tmpfs` into a
64-KiB userspace buffer and writing it to persistent storage is a copy. The
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

### 2. Directory-ingestion processor

Add `utility/file-uploader/streaming_directory_upload_processor.py`. It owns:

* request validation and channel preparation;
* recursive filesystem observation and reconciliation;
* safe relative-path reconstruction;
* bounded scheduling and worker concurrency;
* destination-side temporary files, durability, atomic installation, and
  source deletion;
* JSON Lines progress events; and
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
* Document and test that the shared API mount is ephemeral. The processor can
  guarantee that its staging directory is below the allocated API request
  directory, but it cannot make a Docker named volume become `tmpfs`. A Linux
  deployment that requires RAM-backed staging must mount the shared API volume
  from host `/dev/shm`, or use an equivalent shareable tmpfs-backed volume, in
  every client and service container.
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

### Components reused as-is

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
* a 1-MiB bounded final-result capture;
* bounded final-result retention; and
* whole-request and session-lock cleanup.

The executor intentionally remains unaware of directories, inotify, workers,
progress messages, and destination persistence.

### Existing extension points used

The v1 handshake requires `input`, `input_type`, `result`, and `result_type`,
but permits additional fields. The directory processor returns:

```json
{
  "input": "/api/.../deferred-.../input",
  "input_type": "DIRECTORY",
  "status": "/api/.../deferred-.../status",
  "status_type": "FIFO",
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
applies FIFO checks to its required `input` and `result` fields today, so no
common-code change is necessary. The processor must therefore perform strict
post-creation checks on its directory and status FIFO. A later hardening change
may teach the launcher to validate all typed report fields and containment, but
that is not a prerequisite for issue 122 and should be made as a separate,
backward-compatible common-infrastructure change.

### Components not reused

`streaming_file_upload_processor.py` is not expanded with a second code path.
Its single FIFO maps to one destination file, whereas directory ingestion needs
event observation, a scheduler, per-path state, progress publication, and a
completion barrier. Combining them would weaken validation and make both
processors harder to reason about. Small pure helpers may be factored out only
after their contracts are identical in code, not speculatively.

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
| `WaitInitialQueryTimeoutSec` | `60` | Maximum wait for the first accepted filesystem activity. |
| `WaitQueryUpdateTimeoutSec` | `5` | Quiet period after activity which commits an empty staging tree as complete. |
| `WaitResultConsumptionTimeoutSec` | `60` | Existing final-result retention period. |
| `SESSION_ID` | `default` | Existing deferred-request correlation and duplicate lock. |

`destination/preferred_directory` is the ingestion root. All paths placed in
`input` are reproduced relative to that root. `preferred_directory` must be a
base name, not an absolute or multi-component path. The final root must not
exist at preflight. Because the existing channel-preparation call intentionally
does not receive business arguments, this check can race after the handshake.
Normal processor startup takes an atomic, destination-side reservation for the
name; a lost race is returned as a business conflict before any input is
deleted. V1 never overwrites an existing file, directory, or symlink.

`file_regex` is compiled during preflight and applied with full-match semantics
to the normalized relative path, never an absolute host or container path. The
default `.*` accepts every regular file. Invalid expressions and expressions
over the configured pattern-length limit are rejected before allocation. A
closed file that does not match is reported as `file_skipped` and removed from
staging without being created below the destination. Directories are still
reproduced, including empty directories, so filtering affects files only. A
skipped file does not contribute to the file totals or byte totals in the final
result.

The status protocol is UTF-8 JSON Lines. Every record must fit within
`PIPE_BUF`, and only one publisher thread writes the FIFO. Example records are:

```json
{"event":"file_completed","worker_id":"worker-2","path":"src/main.py","bytes":8431,"files_completed":"7/9","bytes_completed":91820}
{"event":"file_failed","worker_id":"worker-1","path":"data.bin","error_code":"EIO","error_description":"..."}
{"event":"complete","worker_id":null,"files_completed":"12/12","directories_completed":"4/4","bytes_completed":105321}
```

Paths in events are slash-separated paths relative to the staging root. Error
text is length-bounded so a record remains atomic. Consumers terminate on the
`complete`, `failed`, or `cancelled` event and subsequent FIFO EOF; a magic
`EOF_ALL_DONE` payload is unnecessary and could collide with application data.
Each worker has a stable request-local ID (`worker-0` through
`worker-(workers-1)`) included in every file event. Events produced by the
monitor or dispatcher rather than a pool worker, including terminal events and
`file_skipped`, use JSON `null` as `worker_id`.

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
  "files_failed_path": []
}
```

The progress fields are strings in `completed/total` form. During ingestion,
the denominator is the number discovered so far and can increase; in the final
result it is fixed. The denominator of `files_completed` and `files_failed` is
the same total number of regular files accepted by `file_regex`.
`directories_completed` uses the total number of discovered directories.
`files_failed_path` contains every failed file's normalized relative path, in
lexical order, and is empty on success. Admission limits must account for these
paths and reject a request before the final result could exceed the deferred
executor's 1-MiB output limit; the list is never silently truncated.

Progress is best-effort observability; the final result is authoritative.
Failure to attach a status reader must not stop ingestion or fill unbounded
memory. The status publisher keeps a bounded queue, coalesces aggregate
progress when necessary, and always attempts to retain the terminal event.

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
   directory, and starts the existing detached executor.
5. The executor invokes `--prepare-api-channel`. The processor validates the
   canonical request directory, creates `input` as mode `02770` directory and
   `status` as mode `0660` FIFO, verifies their node types without following a
   symlink, and returns its channel report.
6. The executor creates `async_result`, adds it to the report, and returns the
   report to the launcher. The launcher publishes it through the existing
   `result.json_<SESSION_ID>` handshake and exits.
7. In parallel with publication, the executor starts the normal processor. The
   processor atomically creates a destination-side reservation and hidden
   temporary root, starts the observer, performs an initial recursive
   reconciliation scan, then accepts work. The scan closes the
   readiness-to-observer race: entries copied after channel creation but before
   watcher startup are not lost.
8. The client starts reading `status` and populates `input`. A file becomes
   eligible only after a close-write event, a move into the tree, or a
   reconciliation scan establishes a stable candidate. Directories are created
   at the destination as they appear so empty directories are preserved.
9. The dispatcher normalizes the relative path, rejects unsafe node types, and
   evaluates `file_regex`. It deletes and reports a closed nonmatching file;
   otherwise it inserts a deduplicated task into a bounded `queue.Queue`. It
   never submits an unbounded number of futures.
10. A fixed worker pool copies each regular file into a temporary file located
    in its destination directory using a reusable 64-KiB buffer. It flushes and
    `fsync`s the file, installs it without overwrite, `fsync`s the parent
    directory, and only then unlinks the source. Failed sources remain in
    staging for diagnosis until whole-request cleanup.
11. The observer resets the update deadline for every accepted create, close,
    move, or deletion event. Periodic reconciliation discovers events missed
    through startup races or inotify queue overflow.
12. Before the first accepted activity, initial-timeout expiry cancels the
    request without committing a destination tree. After activity, completion
    requires all of: the update quiet period elapsed, the task queue is empty,
    no worker is active, reconciliation finds no regular files, and all pending
    status records have been handed to the bounded publisher.
13. On completion, the processor uses a non-overwriting rename to install its
    temporary destination root at the reserved final name, releases the
    reservation, emits a terminal status event, closes the status FIFO, and
    writes only the final JSON object to stdout.
14. The unchanged executor captures that object, publishes it through
    `async_result`, and applies `WaitResultConsumptionTimeoutSec`. Consumption,
    retention expiry, cancellation, or shutdown removes the complete request
    directory and releases the existing session lock.

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

1. the complete contents were copied;
2. the source identity and size still match the eligible closed file;
3. the destination temporary file was flushed and `fsync`ed;
4. non-overwriting installation succeeded; and
5. the destination parent directory was `fsync`ed.

The final destination tree is built under a hidden sibling temporary root. An
exclusive hidden reservation prevents cooperating requests from claiming the
same name. Successful request completion uses a Linux non-overwriting rename
(`renameat2(..., RENAME_NOREPLACE)`, wrapped and tested explicitly) to publish
the root, so a non-cooperating writer cannot be overwritten between preflight
and commit. On failure, the reservation and temporary destination root are
removed, so clients never observe a partially successful final tree. This
request-level atomicity costs no second full copy because the temporary and
final roots share the same persistent filesystem.

### Resource bounds and backpressure

Memory is bounded by `workers * 64 KiB`, queue metadata, path-state metadata,
and a fixed status-event queue; it is not proportional to file contents. It can
still grow with the number of path names unless admission bounds are defined.
V1 therefore sets limits for maximum relative-path bytes, depth, files,
directories, and total observed bytes. Crossing a limit stops acceptance and
returns a business error.

A bounded task queue applies backpressure to reconciliation. The event callback
must remain short and may mark a rescan-needed flag rather than block the
watchdog dispatcher. Inotify overflow also sets that flag. Reconciliation is
the source of truth; notifications are latency hints.

### Status FIFO behavior

Workers never write the FIFO directly. They enqueue compact status objects and
a single publisher serializes them. It opens/writes non-blockingly, tolerates a
late or absent reader, and cannot delay persistence or processor shutdown.
Individual file events may be coalesced or dropped after the bounded queue is
full. Aggregate counters and the terminal state remain available in the final
result.

## Failure and shutdown behavior

* A per-file failure stops new scheduling, lets in-flight workers reach a safe
  boundary, emits `failed`, and returns a nonzero business result. No source is
  deleted before its own durable installation.
* Observer startup failure and inotify watch exhaustion are business failures,
  not silent fallback. Inotify queue overflow triggers reconciliation; repeated
  overflow that prevents convergence fails the request.
* Processor `SIGTERM` stops observation and scheduling, wakes the monitor,
  cancels pending tasks, joins workers for a bounded period, removes its hidden
  destination root, closes status, and exits. Signal handlers only set/wake a
  stop condition.
* The existing executor terminates and reaps the processor, removes the request
  directory, and releases the session lock. Existing `api_management.py`
  executor discovery and shutdown ordering are reused unchanged.
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
                                          -> FILE_READY -> QUEUED -> COPYING
                                               -> DURABLE -> SOURCE_REMOVED
                                               -> FAILED
                                          -> UPDATE_QUIET
                                               -> RECONCILE
                                                    -> WORK_REMAINS -> ACCEPTING
                                                    -> QUEUE_EMPTY + NO_ACTIVE_WORK
                                                         -> FINAL_TREE_COMMITTED
                                                              -> STATUS_TERMINAL
                                                                   -> RESULT_CAPTURED
                                                                        -> RESULT_CONSUMED
                                                                             -> CLEANED
                                                                        -> RESULT_EXPIRED
                                                                             -> CLEANED
                 -> SERVICE_STOP -> CANCELLED -> CLEANED
```

Only the monitor may transition from accepting work to final commit. It checks
the quiet deadline, dispatcher generation, queue unfinished count, active-worker
count, reconciliation result, and stop flag under one synchronization policy.
An event racing the quiet deadline either increments the generation before the
commit snapshot and is processed, or arrives after watcher shutdown and is
rejected by the closing staging directory.

## Rejected alternatives

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

### Let every worker write `status` directly

Rejected because writes larger than `PIPE_BUF` can interleave, a missing reader
can block all workers, and worker scheduling then becomes coupled to
observability. One nonblocking publisher gives the protocol a clear owner.

### Treat inotify as a complete event log

Rejected because watches are installed asynchronously, queues can overflow,
and recursive watching has directory-creation races. Initial and periodic
reconciliation are necessary for correctness.

### Install each file directly into the public final root

Rejected for v1 because a failed request would expose a partial tree. A hidden
destination-side root plus final rename provides request-level atomic visibility
without duplicating file contents.

## Implementation sequence

1. Add schema and generated executor; assert generated paths and parameters.
2. Implement processor argument validation and channel preparation; test node
   types, modes, containment, and readiness report fields.
3. Implement safe reconciliation and single-worker durable copy; test nested
   and empty directories, binary/large files, conflicts, and unsafe nodes.
4. Add recursive observation, deduplication, bounded queue, and worker pool;
   test files arriving before watcher startup, during copying, and by rename.
5. Add status publisher and completion monitor; test absent/slow readers,
   atomic records, burst gaps, initial timeout, update quiet period, and races.
6. Add request-level destination commit and rollback; inject copy, fsync,
   rename, observer, and limit failures.
7. Exercise the generated pseudo-filesystem API under Compose and verify
   shutdown during initial wait, active copying, quiet detection, result wait,
   and a disconnected writer leaves no processes or request artifacts.

## Minimum acceptance tests

Implementation is complete only when automated coverage includes:

* the existing `streaming_file_upload` query remaining unchanged;
* the new query using the existing launcher/executor and returning all six
  channel fields plus the protocol version;
* invalid metadata, destination, preferred directory, worker count,
  `file_regex`, conflict policy, timeout, and duplicate session rejection before
  request allocation;
* staging directory and status/result FIFO types, permissions, containment,
  uniqueness, and cleanup;
* a producer copying before observer startup, incremental close-write, atomic
  move-in, dynamically created nested directories, empty directories, and
  reconciliation after simulated inotify overflow;
* arbitrary safe filenames including spaces and newlines, with JSON escaping;
* the default `.*` copying all regular files, selective relative-path matching,
  nested-path full-match behavior, excluded-file deletion and `file_skipped`
  status, and empty-directory preservation under filtering;
* rejection of traversal, symlinks, hard links, FIFOs, sockets, devices, and
  source identity changes while queued or copied;
* binary files, empty files, files larger than `PIPE_BUF`, many small files,
  total input larger than available process memory, and worker concurrency;
* destination non-overwrite behavior, per-file durability ordering, source
  deletion only after durable installation, final atomic tree publication, and
  rollback after injected failure;
* initial silence cancellation, activity-reset update timing, bursts whose
  total duration exceeds the update timeout, and no premature completion while
  work is queued or active;
* a first event racing initial timeout and a new event racing final quiet
  detection, each with exactly one valid transition;
* status records from one publisher, stable request-local `worker_id` values,
  null worker IDs on dispatcher/monitor events, records no larger than
  `PIPE_BUF`, a late reader, no reader, slow reader, queue coalescing, terminal
  event, and FIFO EOF;
* final success/error JSON, completed/total ratios, and the lexically ordered
  complete `files_failed_path` array delivered unchanged through
  `async_result`, plus rejection before the final result can exceed 1 MiB and
  result-retention expiry;
* admission-limit, observer-startup, queue-overflow, copy, fsync, and final
  rename failures producing bounded errors without a public partial tree; and
* service termination in every lifecycle phase reaping the processor and
  workers and leaving no staging directory, FIFO, session lock, hidden
  destination tree, or deferred executor.

## Decisions fixed by this review

1. The feature is a new file-uploader query, not a new service and not a mode
   added to the single-file query.
2. The common launcher, executor, API management, and API generators require no
   behavioral changes for v1.
3. The processor chooses a directory input transport and an additional FIFO
   progress transport through the extensible readiness report.
4. Processor stdout contains exactly one final bounded result; status is a
   separate best-effort JSON Lines stream.
5. Completion uses initial and update inactivity timeouts plus a fully drained,
   reconciled system. Empty staging alone is insufficient.
6. Source deletion follows durable non-overwriting destination installation.
7. The complete destination tree becomes visible atomically at request success.
8. Inotify accelerates discovery; reconciliation establishes correctness.
9. RAM-backed behavior is a mount/deployment property and must be configured
   and verified rather than inferred from an `/api` pathname.

## Follow-up decisions before coding

The implementation PR should choose and record concrete defaults for maximum
path length, depth, file count, directory count, total bytes, task-queue size,
status-queue size, reconciliation interval, and bounded worker shutdown. It
should also decide whether the functional Compose environment can reliably
provision a shareable tmpfs-backed volume in CI; if not, correctness tests may
use a normal volume while a Linux-only mount test verifies the deployment
recipe separately.
