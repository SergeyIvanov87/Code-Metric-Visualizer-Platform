# Kafka capture event schema, version 1

All events use `CAPTURE_ID` as the Kafka key and contain `schema_version`,
`capture_id`, and `type`.

- `connection_log`: includes `trace_id`, sanitized `filename`, and
  `payload_base64` containing reconstructed newline-delimited syslog records.
- `capture_complete`: terminal marker produced only after all connection logs
  have been acknowledged during producer flush.
- `capture_failed`: terminal infrastructure failure with a bounded `error`
  diagnostic.

Using one key keeps a bounded capture ordered in one partition. Event IDs and
per-segment publishing remain future work for the session-aware architecture;
the current contract transports the existing bounded-batch behavior without
putting pytest interpretation in the tap subscriber.

## Initialization timeout

`capture_start_timeout` is emitted when no downstream capture bytes arrive
within `WAIT_MSEC_BEFORE_START`. It contains `wait_msec` and `exit_code: 10`.
This terminal event is distinct from `capture_failed`: the tap and broker were
reachable, but the expected test traffic never started during the configured
admission interval. Consumers must treat it as an infrastructure/orchestration
error and must not interpret it as a successful empty test run.
