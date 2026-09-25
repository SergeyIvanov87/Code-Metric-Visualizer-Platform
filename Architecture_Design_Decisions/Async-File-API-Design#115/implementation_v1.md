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
result as JSON, including `received_bytes` so callers can compare the reported
byte count with the persisted file size. Known preferred-filename conflicts are
rejected before request allocation; if a conflict appears after the handshake,
the processor drains the input before returning the conflict result.

### Deferred launcher

`common/deferred_query_launcher.py` performs the short-lived allocation phase:

1. validate timeouts, session, executables, and processor arguments;
2. reject duplicate active session IDs;
3. atomically create a unique request directory;
4. start a detached deferred executor;
5. wait for its JSON report on the private readiness channel;
6. require the four channel fields and validate endpoints declared as FIFOs; and
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
2. receive the processor's JSON channel report containing at least `input` and
   `input_type`;
3. prepare the executor-owned result FIFO;
4. append `result` and `result_type` to the report;
5. send that JSON report to the launcher through the readiness descriptor;
6. run and supervise the processor;
7. capture at most 1 MiB of processor output;
8. publish the result for a bounded period; and
9. remove the request directory and session lock.

The public readiness report uses transport-neutral field names. The current
uploader reports `input_type` as `FIFO`, and the executor reports `result_type`
as `FIFO`. The launcher requires `input`, `input_type`, `result`, and
`result_type`, but permits additional fields so processors and executors can add
metadata without breaking the handshake. For channels whose type is `FIFO`
(case-insensitive), the launcher verifies that the reported path is a FIFO.
Other declared channel types are passed through without FIFO-specific checks.
The result publisher itself remains FIFO-specific, so the schema is extensible
even though the complete executor lifecycle does not yet support arbitrary
result transports.

Thus the executor **delivers** the communication-channel selection; it does not
make the business processor input-channel decision.

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
* Readiness is reported only after the communication endpoints exist, and the
  four required report fields can be extended with additional metadata.
* The launcher is short-lived while the detached executor owns the request.
* Processor output is bounded and retained independently of processor lifetime.
* Successful uploads, including empty files, report the number of bytes
  received.
* Query arguments are parsed strictly as name/value pairs, so values that match
  parameter names remain valid.
* Uploaded files are installed atomically without an extra full-size staging
  copy in the request directory.
* Completion, timeout, and shutdown attempt to remove the whole request.
* Functional coverage includes validation, empty uploads, initial and
  update-silence timeouts, duplicate sessions, argument-name collisions,
  preferred-filename conflict races, binary data larger than `PIPE_BUF`,
  generated API execution, and shutdown artifact detection.

## Differences from `Review.md`

The implementation evolved from the exact sequence originally recorded in the
ADR:

* `Review.md` assigns input FIFO creation and upload framing to the generic
  executor. V1 instead lets the processor prepare and consume its chosen input
  channel. This keeps transport-specific business integration out of the
  executor, but requires processors to implement the preparation contract.
* The ADR describes a plain input-path handshake. V1 returns an extensible JSON
  object with required `input`, `input_type`, `result`, and `result_type` fields,
  allowing the launcher to deliver the complete per-request channel description
  while accepting additional metadata.
* The ADR launches the processor after the executor has committed all input. V1
  starts the processor to consume its own channel directly, avoiding a second
  complete upload copy.
* The executor option named `--input` currently carries the request directory,
  not an input path; `--request-directory` would describe it more accurately.

## Known gaps

* Update silence currently cancels the upload instead of committing bytes
  already received as required by `Review.md`.
* Shutdown removes ordinary API directories before deferred executors are fully
  reaped, which can race executor cleanup.
* The readiness field names now describe paths and types without embedding FIFO
  in each key. However, only FIFO channels are verified, the executor-owned
  result endpoint and publisher remain FIFO-specific, and behavior for other
  declared types is not yet defined.
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
* The extensible JSON readiness report gives clients both endpoints and their
  declared transport types explicitly.
* Sixty-second interactive defaults reduce premature cleanup during manual use.
* PID registration, bounded shutdown, and CI artifact checks improve
  operational visibility.

### Worse or incomplete

* The processor contract is more complex because each processor must prepare
  and consume its own channel.
* The report schema no longer embeds FIFO in field names, but the executor-owned
  result channel and publisher still constrain the lifecycle to a FIFO result.
* Direct streaming couples the business processor's lifetime to slow or failed
  clients.
* Update-timeout behavior does not yet conform to the ADR.
* Lifecycle and permission testing remains incomplete.

## Overall assessment

Version 1 achieves the primary end-to-end upload goal and establishes a useful
general-purpose deferred lifecycle. Its key architectural boundary should be
preserved: the business processor selects and prepares its input communication
channel, while the deferred executor supervises the request and relays the JSON
channel report to the launcher through readiness.

The next version should define validation and lifecycle behavior for non-FIFO
channel types, reconcile update-timeout semantics with the ADR, reorder
shutdown cleanup, rename the executor request-directory
option, and complete the ADR acceptance-test matrix.
