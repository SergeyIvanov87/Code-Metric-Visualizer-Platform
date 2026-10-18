---
name: streaming-ingestion
description: Use when modifying streaming file upload, directory upload, shared-staging directory events, readiness event parsing, sealing, backpressure, or deferred upload cleanup.
---

# Maintain streaming ingestion

Read [the upload protocol](../../../utility/file-uploader/README.md) and the matching schema in `utility/file-uploader/API` first.

1. Choose the correct operation. File upload installs one byte stream and can validate `expected_bytes`. Directory upload transfers stable files through nested file uploads. Directory events reports readiness in shared staging and does not copy to `/uploads`.
2. Change the matching `utility/file-uploader/streaming_*_processor.py`, API schema, and functional tests together. Reuse the common deferred launcher/executor lifecycle rather than creating an independent request owner.
3. Preserve producer visibility across API-volume mount paths. Directory-events `input` is a relative symlink into sibling `.staging`; directory-upload `input` is a real request-local directory. Producers should atomically rename completed files from excluded temporary paths.
4. Preserve JSON-Line event framing: buffer through newline, validate batch sequence bounds and increasing sequence numbers, and continue across batches until termination/EOF. Use `common/modules/directory_event_protocol.py`; a single FIFO read is not necessarily a complete record.
5. Keep readiness separate from consumer completion and durability. Preserve pending event backlogs for slow/absent readers. The final result reports delivery counts; unread events must not prevent sealing. A `transport_closed` record is a cleanup notification, not a ready-file event.
6. Preserve explicit non-empty `seal` messages and update-timeout reconciliation. The result-consumption timeout begins after processing and controls final-result availability.
7. Preserve filtering, path/admission limits, and rejection of traversal, destination conflicts, symlinks, hard links, and special nodes. Directory-upload staging is request-scoped; shared event staging survives request cleanup. Never follow the `input` link during cleanup.

## Verify

```sh
python -m pytest -q common/test_directory_event_protocol.py common/test_deferred_query_executor.py
```

Then run the file-uploader functional suite using [test diagnostics](../container-test-diagnostics/SKILL.md). Select cases for slow/no readers, partial records, concurrent sessions, mount-path differences, seal, timeout, and shutdown based on the changed behavior. Do not infer end-to-end transfer success from a readiness event.

## Architecture references

Choose the record for the operation being changed:

- [Async upload implementation recap](../../../Architecture_Design_Decisions/Async-File-API-Design%23115/implementation_v1.md): common deferred lifecycle and the separation between upload business rules and transport ownership.
- [Bulk-directory implementation v1](../../../Architecture_Design_Decisions/Bulk-Directory-Ingestion%23122/implementation_v1.md): nested upload acknowledgement, exact byte-count checks before source deletion, worker allocation, polling costs, and the performance experiment/rollback. Read this before changing concurrency or durability. Benchmark results and TODOs describe that version, not guarantees for the current checkout.
- [Bulk-directory design review](../../../Architecture_Design_Decisions/Bulk-Directory-Ingestion%23122/Review.md): rationale and failure/acceptance scenarios. Its shared-tmpfs input and `PIPE_BUF`-bounded final-result design differ from the implemented request-local directory and streamed result; use the implementation recap and current code for those contracts.
- [Shared-staging event-delivery decision](../../../Architecture_Design_Decisions/Bulk-Directory-Ingestion%23122/implementation_v2_event_delivery.md): why readiness notification is separate from durable upload, relative mount paths, JSON-Line batches, sealing, and staging lifetime. It also discusses proposed acknowledgement, replay, and retention options; do not assume those options exist in the current endpoint.

These records explain different operations and revisions, not interchangeable modes. Check the current upload README, schemas, processors, and tests before carrying a recorded recommendation into a fix.

## Example

For “files disappear after event-session cleanup,” inspect `.staging` ownership and symlink-safe cleanup, rather than extending the result-consumption timeout.
