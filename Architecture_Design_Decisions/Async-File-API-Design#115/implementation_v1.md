# Issue 115: implementation v1 recap

## Scope

Version 1 adds a streaming file-upload query and a reusable deferred-execution
lifecycle. It proves that long-running, two-phase requests can use the existing
pseudo-filesystem API without adding an async path prefix or changing the common
API generators.

The implementation deliberately separates two concerns:

* the **deferred executor** is general-purpose lifecycle infrastructure; and
* the **streaming file-upload processor** owns the upload business rules and
  selects/prepares its input communication channel.

## Implemented components

### Streaming file uploader

`utility/file-uploader` exposes `POST +/streaming_file_upload`. Its schema
contains `metadata`, `preferred_filename`, `destination`, `SESSION_ID`, and the
three ADR timeouts:

* `WaitInitialQueryTimeoutSec` (60 seconds);
* `WaitQueryUpdateTimeoutSec` (5 seconds); and
* `WaitResultConsumptionTimeoutSec` (60 seconds).

The processor validates metadata, filenames, and the destination. It prepares
its input channel, consumes binary upload data, writes to a temporary file in
the destination, calls `fsync`, and installs the completed file atomically
without overwriting an existing preferred filename. It returns the business
result as JSON.

### Deferred launcher

`common/deferred_query_launcher.py` performs the short-lived allocation phase:

1. validate timeouts, session, executables, and processor arguments;
2. reject duplicate active session IDs;
3. atomically create a unique request directory;
4. start a detached deferred executor;
5. wait for its JSON report on the private readiness channel;
6. validate the reported paths; and
7. return the report to the API client.

The launcher exits after the handshake, so the generated API service does not
wait for upload processing or result consumption.

### General-purpose deferred executor

`common/deferred_query_executor.py` owns process lifetime, bounded output
capture, result retention, signal handling, and request cleanup. It must not
contain file-upload business rules or choose the processor's input transport.
A processor may select a FIFO now, while another processor could prepare a
different communication mechanism later.

The contract is:

1. ask the processor to prepare and describe its selected input channel;
2. receive the processor's JSON channel report;
3. prepare the executor-owned result endpoint;
4. complete the report with `input_FIFO` and `result_FIFO`;
5. send that JSON report to the launcher through the readiness descriptor;
6. run and supervise the processor;
7. capture at most 1 MiB of processor output;
8. publish the result for a bounded period; and
9. remove the request directory and session lock.

Thus the executor **delivers** the communication-channel selection; it does not
make the business processor's input-channel decision. The current v1 report and
launcher validation use FIFO-specific field names and node checks. Supporting a
non-FIFO channel later will require generalizing that public report and its
validation, but not moving channel selection into the executor.

### Shutdown and CI

`common/api_management.py` discovers registered deferred executors, signals
them, waits for bounded cleanup, escalates when necessary, and removes remaining
request/session artifacts. The dedicated functional job runs the generated
filesystem API and checks that `exec`, `result*`, `input`, and `async_result`
artifacts do not survive container shutdown.

## Targets achieved

* Existing pseudo-filesystem paths and generators remain in use.
* Binary file data is streamed outside the line-oriented `exec` arguments.
* Every request receives an atomic unique directory with an encoded session
  component and stable channel names.
* Invalid transport and business arguments are rejected before request
  allocation.
* Duplicate active sessions are rejected.
* Readiness is reported only after the communication endpoints exist.
* The launcher is short-lived while the detached executor owns the request.
* Processor output is bounded and retained independently of processor lifetime.
* Uploaded files are installed atomically without an extra full-size staging
  copy in the request directory.
* Completion, timeout, and shutdown attempt to remove the whole request.
* Functional coverage includes validation, initial timeout, duplicate sessions,
  binary data larger than `PIPE_BUF`, generated API execution, and shutdown
  artifact detection.

## Differences from `Review.md`

The implementation evolved from the exact sequence originally recorded in the
ADR:

* `Review.md` assigns input FIFO creation and upload framing to the generic
  executor. V1 instead lets the processor prepare and consume its chosen input
  channel. This keeps transport-specific business integration out of the
  executor, but requires processors to implement the preparation contract.
* The ADR describes a plain input-path handshake. V1 returns JSON containing
  `input_FIFO` and `result_FIFO`, allowing the launcher to deliver the complete
  per-request channel description.
* The ADR launches the processor after the executor has committed all input. V1
  starts the processor to consume its own channel directly, avoiding a second
  complete upload copy.
* The executor option named `--input` currently carries the request directory,
  not an input path; `--request-directory` would describe it more accurately.

## Known gaps

* Update silence currently cancels the upload instead of committing bytes
  already received as required by `Review.md`.
* An empty upload is indistinguishable from initial silence and times out.
* Shutdown removes ordinary API directories before deferred executors are fully
  reaped, which can race executor cleanup.
* The FIFO-specific readiness fields and launcher checks do not yet realize the
  full goal of allowing arbitrary processor-selected channel types.
* Tests do not yet cover all timeout races, slow multi-chunk uploads, result
  retention expiry, processor failures, hostile-client permissions, or shutdown
  during every lifecycle state.
* Length/digest integrity and retry idempotency remain undefined.

## Evaluation

### Better

* Responsibilities are clearer: the executor manages lifecycle, while the
  processor owns business validation, persistence, and input-channel selection.
* Streaming directly into the destination-side temporary file avoids duplicate
  full-size upload storage and I/O.
* The JSON readiness report gives clients both request endpoints explicitly.
* Sixty-second interactive defaults reduce premature cleanup during manual use.
* PID registration, bounded shutdown, and CI artifact checks improve
  operational visibility.

### Worse or incomplete

* The processor contract is more complex because each processor must prepare
  and consume its own channel.
* The present `input_FIFO`/`result_FIFO` protocol and FIFO validation still
  constrain an architecture intended to allow other communication mechanisms.
* Direct streaming couples the business processor's lifetime to slow or failed
  clients.
* Update-timeout and empty-file behavior do not yet conform to the ADR.
* Lifecycle and permission testing remains incomplete.

## Overall assessment

Version 1 achieves the primary end-to-end upload goal and establishes a useful
general-purpose deferred lifecycle. Its key architectural boundary should be
preserved: the business processor selects and prepares its input communication
channel, while the deferred executor supervises the request and relays the JSON
channel report to the launcher through readiness.

The next version should generalize the readiness schema beyond FIFO-only
validation, correct update-timeout and empty-input semantics, reorder shutdown
cleanup, rename the executor's request-directory option, and complete the ADR's
acceptance-test matrix.
