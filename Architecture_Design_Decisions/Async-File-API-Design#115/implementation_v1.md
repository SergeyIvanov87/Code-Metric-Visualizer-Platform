# Issue 115: implementation v1 recap and design-conformance review

## Purpose and scope

This document records what the first implementation of the asynchronous file
upload design actually delivers. It compares commit `c30e46e` with the selected
design in [`Review.md`](Review.md), rather than restating the intended design as
if every part had been implemented.

The implementation is a useful end-to-end prototype, but it is **not yet a
fully conforming implementation of the decision record**. In particular, later
review-driven changes deliberately transferred input-channel creation and
upload framing from the generic deferred executor to the file-uploader
processor. Some of the minimum acceptance matrix also remains unimplemented.

## What has been implemented

### Streaming file-uploader container

The new `utility/file-uploader` container provides one opt-in `POST` query at
`+/streaming_file_upload`. Its schema declares:

* `metadata`, which must be empty or a JSON object;
* `preferred_filename`, which may be empty to request a generated name;
* `destination`, an existing writable directory in the container;
* `WaitInitialQueryTimeoutSec` (default 60 seconds);
* `WaitQueryUpdateTimeoutSec` (default 5 seconds);
* `WaitResultConsumptionTimeoutSec` (default 60 seconds); and
* `SESSION_ID` (default `default`).

The query uses the normal pseudo-filesystem generator and method directory. No
new async URL prefix or common generator branch was added. The generated query
executor calls the common deferred launcher and returns a JSON handshake with
the per-request `input_FIFO` and `result_FIFO` paths.

The upload processor validates the business arguments, creates the input FIFO,
reads binary content from it, and writes to a destination-side temporary file.
It flushes and `fsync`s that file, then installs it by a non-overwriting hard
link and removes the temporary name. A caller may select a safe base filename,
or allow generation of an `uploaded.<UTC timestamp>` name with collision
suffixes. The JSON business result includes `error_code`,
`error_description`, metadata, destination path, and size.

### Common deferred request lifecycle

`common/deferred_query_launcher.py` now:

1. parses and validates the three positive, bounded timeout values and a safe
   `SESSION_ID`;
2. checks that the API directory, processor, and executor are valid;
3. invokes the processor's `--check-arguments` mode before allocation;
4. rejects a duplicate active session through an atomic session-lock directory;
5. atomically allocates `deferred-<encoded-session>-<unique-suffix>` beneath the
   query's `POST` directory;
6. starts the executor in a new process session with inherited server streams
   redirected;
7. waits on a private readiness pipe; and
8. validates the two reported paths and FIFO node types before printing the
   JSON handshake.

`common/deferred_query_executor.py` owns the long-lived lifecycle. It registers
its PID and request information, asks the processor to prepare the input
channel, creates `async_result`, publishes readiness, starts the processor,
captures at most 1 MiB of combined processor output, publishes that result with
a bounded wait, and removes the request directory and session lock in a
`finally` block.

Unlike the original design, the processor—not the executor—opens and drains the
input FIFO and enforces upload inactivity timeouts. This avoids a second full
upload copy: uploaded bytes go directly from the FIFO into the processor's
atomic destination-side temporary file. Only the small, bounded processor
result is staged as `processor_result` so processing can finish before a result
reader connects.

### Shutdown integration

`common/api_management.py` discovers executors using the `executor.json`
registration plus `/proc/<pid>/cmdline` verification, rather than a broad
process-name match. It sends `SIGTERM`, waits for a bounded interval, escalates
remaining processes with `SIGKILL`, and removes registered request and session
lock paths. The uploader CI scenario intentionally leaves a request active so
the post-container artifact check can detect leaked `input` or `async_result`
FIFOs.

### Automated coverage and CI

The functional tests currently cover:

* invalid generic timeout and invalid processor metadata before allocation;
* initial-input timeout and cleanup without a destination file;
* atomic unique request creation and stable FIFO names;
* readiness publication only after both FIFO nodes are visible;
* duplicate active-session rejection;
* binary data containing NULs and newlines and larger than `PIPE_BUF`;
* a successful business result and persisted file contents;
* schema routes, parameters, and the two 60-second defaults;
* schema-encoded empty optional values;
* processor ownership of only the input FIFO during channel preparation;
* handling `--check-arguments` as file data rather than a control flag;
* execution through the real generated container filesystem API; and
* shutdown artifact detection in the dedicated GitHub Actions job.

## Design targets achieved

| Design target | Status | Evaluation |
| --- | --- | --- |
| Opt-in behavior without an async path prefix | Achieved | The query uses the established schema and generator flow; unrelated queries are not changed to deferred behavior. |
| Binary data excluded from `exec` argv | Achieved | Only metadata travels through normal arguments; file bytes travel through the unique input FIFO. |
| Three declared timeout parameters | Achieved | All are ordinary schema parameters and can be overridden by the existing request machinery. Initial and result defaults were raised from the design example to 60 seconds for interactive use. |
| Validation before artifact allocation | Substantially achieved | Transport values, executable paths, and uploader business arguments are checked before the request and lock are created. There are no optional size/concurrency admission controls. |
| Atomic unique request identity | Achieved | `mkdtemp` supplies a unique suffix and the encoded session is included for diagnosis. FIFO names remain stable inside the directory. |
| Duplicate session protection | Achieved | An atomic per-session lock rejects another live request with the same `SESSION_ID`. |
| Detached long-lived owner | Achieved for the intended server interaction | The launcher starts the executor in a new session, redirects inherited standard streams, returns after readiness, and does not wait for the upload lifecycle. |
| Readiness-gated handshake | Achieved, with an evolved contract | Both FIFO paths and types are checked before a JSON handshake is printed. |
| No full-size upload staging in the request directory | Achieved as an improvement over an intermediate implementation | The processor streams directly from `input` into its atomic destination temporary file. |
| Bounded business-result capture | Achieved | Capture is limited to 1 MiB and an oversized producer is terminated. |
| Result retention and eventual cleanup | Achieved for normal tested paths | Publishing is time-bounded and the request directory is removed after consumption or expiry. |
| Exact shutdown discovery | Achieved | Registrations and command-line verification replace imprecise substring-only signalling. |
| Container-level functional exercise | Achieved | A dedicated Compose test drives the generated pseudo-filesystem API, and CI checks for leaked API artifacts. |

## Conditions met from `Review.md`

The following selected-design conditions are present in v1:

* existing API generation and parameter-file machinery are reused;
* uploaded bytes are streamed by the client rather than represented as a host
  pathname or line-oriented argument;
* a unique directory correlates the input and output FIFO;
* `SESSION_ID` is encoded in the directory name and not repeated in stable FIFO
  names;
* malformed timeout, session, executable, and uploader arguments are rejected
  before the unique request directory is allocated;
* the launcher/executor handoff uses a private readiness descriptor;
* inherited standard streams do not keep generated-server command substitution
  open;
* processor invocation uses an argv vector without a shell;
* uploader persistence is atomic and does not overwrite a requested existing
  filename;
* processor output is retained separately from processor lifetime and bounded;
* normal completion, upload cancellation, result expiry, and executor shutdown
  all attempt idempotent removal of the whole request directory; and
* active executors are registered for service-shutdown cleanup.

## Deviations and violations against the selected design

### Intentional architectural deviations

These are not merely missing tests; the implementation contract differs from
the text selected in `Review.md`.

1. **The launcher does not create `input`.** The design assigns unique-directory
   and input-FIFO creation to the launcher. V1 creates the directory in the
   launcher, but the uploader processor creates `input` during
   `--prepare-api-channel`.
2. **The generic executor does not ingest or frame uploads.** The design assigns
   FIFO reading and both upload inactivity timers to the generic executor. V1
   launches the processor immediately; that processor opens `input`, reads the
   stream, and owns the initial/update timers.
3. **The executor interface changed.** The design's `--input` value is the input
   FIFO path. V1 passes the request directory under the option named `--input`,
   and the processor independently derives `<request-directory>/input`.
4. **The readiness payload changed.** The selected design says the launcher
   prints the input FIFO path. V1 prints a JSON object with both `input_FIFO` and
   `result_FIFO`. This is more useful to clients, but it is a protocol change.
5. **The processor starts before input completion.** The selected lifecycle has
   the executor accumulate/commit input and then launch the business processor.
   V1 starts a FIFO-aware business processor as soon as channels are ready.
6. **Timeout exit 124 is treated as transport cancellation.** The executor does
   not publish processor output when the processor returns 124. This embeds an
   uploader-specific convention in otherwise generic orchestration.

### Behavioral gaps or violations

1. **Update silence does not commit partial input.** `Review.md` specifies that
   once the first byte arrives, a full update-timeout interval commits the
   accumulated stream as successful input. The current processor raises
   `TimeoutError` for both initial silence and later update silence, returns
   status 124, deletes its temporary file, and causes the executor to omit the
   result. EOF works, but update-timeout framing does not follow the design.
2. **Empty upload is not supported as specified.** Opening and closing the FIFO
   without bytes is treated like “no initial bytes” and eventually times out.
   The acceptance list explicitly requires empty-file coverage.
3. **Shutdown ordering differs from the decision.** The design says to signal
   executors, observe them finish, and then perform ordinary query-directory
   cleanup. The current handler signals executors, removes ordinary API method
   directories, and only then waits/reaps. Removing a parent method directory
   can race an executor that is still cleaning up or processing.
4. **Graceful shutdown is not guaranteed before forced cleanup.** The executor
   signal handler records a flag, but the main thread can be blocked reading
   processor stdout. API management can ultimately kill it and remove files;
   this meets bounded container cleanup, but not the stronger condition that
   every executor first stops and reaps its own processor cleanly.
5. **The API ownership/permissions condition is only partially demonstrated.**
   FIFO modes are set (`0620` for input and `0640` for result), but there is no
   acceptance test proving a client cannot create, replace, or unlink API
   artifacts while retaining the intended FIFO access.
6. **No optional integrity contract is implemented.** There is no declared
   length or digest verification. This was optional per query, so it is a known
   limitation rather than a mandatory v1 defect.
7. **Idempotency is not defined.** Duplicate concurrent sessions are rejected,
   but completed requests have no retained idempotency key and retries may
   create another generated file.

## Acceptance-test coverage still missing

The minimum list in `Review.md` is broader than the six current Python tests.
V1 does not yet provide focused automated evidence for:

* unchanged behavior of a non-opt-in query;
* per-request overrides for all three timeout values through generated parameter
  handling;
* invalid session and executable-path rejection before allocation;
* executor startup failure and readiness-timeout cleanup;
* initial-byte/update-timeout and EOF/chunk race boundaries;
* update-deadline reset across a deliberately slow multi-chunk writer;
* update silence committing already received bytes;
* empty uploads;
* optional length/digest behavior (if the query elects to support it);
* exact forwarding of both success and business-error output;
* non-zero exits, signal termination, oversized output, and long-running
  processors as individual assertions;
* result-consumption timeout and bounded result-side unblocking;
* termination during each of allocation, upload, processing, and delivery;
* proof that no child process or descriptor remains after shutdown; and
* hostile-client permission checks.

The CI artifact scan is valuable end-state evidence, but it is not a substitute
for these state- and race-specific tests.

## Evaluation: what became better

* **Large uploads are no longer copied twice.** Removing the request-local
  `upload` staging file reduces request-directory storage, I/O, and latency. The
  only full copy is the destination-side temporary file required for atomic
  publication.
* **The handshake is self-contained.** Returning both FIFO paths as JSON removes
  the need for a client to derive the result path and makes the protocol easier
  to extend without ambiguous line parsing.
* **Channel ownership is explicit for this service.** The file processor owns
  its specialized input channel, while the generic executor owns result
  retention. This is flexible for processors needing a custom input mechanism.
* **Interactive usability improved.** Sixty-second defaults for initial input
  and result consumption make manual `echo`, `cat`, and `read` workflows much
  less prone to losing transient artifacts.
* **File installation is robust.** Destination-side temporary writing, `fsync`,
  non-overwriting linking, generated-name collision handling, and cleanup on
  interruption are stronger than a direct write to the final path.
* **Operational cleanup has concrete integration.** PID registration,
  `/proc` verification, bounded escalation, a deliberately active shutdown
  request, and a post-stop artifact scan make leaks visible in CI.
* **Validation has a business-specific preflight hook.** Invalid metadata,
  unsafe filenames, and unusable destinations can fail before exposing a
  deferred request to a client.

## Evaluation: what became worse

* **The common abstraction is less generic.** A processor must now understand
  `--request-directory`, `--prepare-api-channel`, `--initial-timeout`, and
  `--update-timeout`, and must implement FIFO framing itself. The selected
  design allowed an ordinary processor to consume a staged path, descriptor, or
  standard input behind a generic executor.
* **Transport policy leaked into business code.** FIFO mechanics and timeout
  behavior live in `streaming_file_upload_processor.py`, increasing duplicated
  work and behavioral drift for every future deferred query.
* **The option name is misleading.** Executor `--input` contains a directory,
  not an input path. This weakens the command-line contract and complicates
  maintenance.
* **Streaming couples persistence to client behavior.** A slow, interrupted, or
  malicious writer keeps the business processor and a destination temporary
  file alive. Staging would cost disk space but would separate transport
  completion from business execution and enable digest/length verification
  before invocation.
* **The timeout semantics regressed.** The most important functional mismatch is
  that update silence cancels instead of committing partial content. This makes
  the current behavior depend on writer EOF and contradicts the selected
  framing rule.
* **The readiness protocol is no longer the documented plain-path contract.**
  JSON is arguably better, but external clients built from `Review.md` alone
  will not interoperate until the decision record is amended.
* **Shutdown relies more on forced external cleanup.** Deleting method
  directories before reaping their active owners is simpler for artifact
  removal but weaker for orderly lifecycle guarantees.

## Overall v1 assessment and recommended next targets

V1 achieves the primary product goal: a client can allocate a unique request,
stream a binary file through a container-visible FIFO, receive the processor's
JSON result asynchronously, and obtain an atomically installed file. It also
demonstrates that the existing pseudo-filesystem generators can host this model
without an async-specific generator branch.

It should nevertheless be labelled a **working prototype with partial design
conformance**, not completion of every issue 115 target. The next iteration
should, in priority order:

1. decide whether the decision record should adopt processor-owned input
   channels and the JSON handshake, or move those responsibilities back to the
   generic executor;
2. make update silence commit received bytes while keeping initial silence a
   cancellation, and define a reliable empty-file signal;
3. reorder shutdown to reap deferred owners before deleting their parent API
   directories, with a wakeable/non-blocking executor supervision loop;
4. rename executor `--input` to `--request-directory` if the evolved contract is
   retained;
5. add the missing lifecycle, race, error, timeout, permission, and non-opt-in
   acceptance tests; and
6. document whether integrity validation and retry idempotency are explicitly
   out of scope or required for v2.

