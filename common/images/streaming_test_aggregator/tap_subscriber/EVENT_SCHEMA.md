# Kafka capture event schema, version 1

All events use `CAPTURE_ID` as the Kafka key and contain `schema_version`,
`capture_id`, and `type`.

- `connection_log_chunk`: includes `trace_id`, sanitized `filename`, a
  zero-based `chunk_index`, and `payload_base64`. Chunks are at most 512 KiB
  before base64 encoding so each event remains below Kafka's default record
  limit.
- `connection_log_complete`: includes `trace_id`, `filename`, and the expected
  `chunk_count`; consumers publish the reconstructed file only after receiving
  this marker. Consumers also accept the original whole-file `connection_log`
  event during rolling upgrades.
- `capture_complete`: terminal marker produced only after all connection logs
  have been acknowledged during producer flush.
- `capture_failed`: terminal infrastructure failure with a bounded `error`
  diagnostic.

Using one key keeps the one-shot capture ordered in one partition. Stable event
IDs and per-segment publishing remain possible hardening work for restart-safe
delivery within an execution; they do not imply a multi-run service. The
current contract transports the finite execution without putting pytest
interpretation in the tap subscriber.

## Initialization timeout

`capture_start_timeout` is emitted when no downstream capture bytes arrive
within `WAIT_MSEC_BEFORE_START`. It contains `wait_msec` and `exit_code: 10`.
This terminal event is distinct from `capture_failed`: the tap and broker were
reachable, but the expected test traffic never started during the configured
admission interval. Consumers must treat it as an infrastructure/orchestration
error and must not interpret it as a successful empty test run.
