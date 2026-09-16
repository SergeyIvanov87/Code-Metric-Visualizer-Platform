# Log event aggregator image

This service is the test analyzer. It consumes `connection_log` records for one
`CAPTURE_ID` from Kafka until it receives `capture_complete`, writes the decoded
connection logs into `/logs/syslog-streams`, and runs its own copy of the
canonical pytest summary analyzer. A `capture_failed` event is treated as an
infrastructure failure rather than a test result. A `capture_start_timeout`
event writes a specific diagnostic and returns distinguishable exit code `10`.

The tap subscriber and this analyzer intentionally do not share source files or
runtime filesystem state. Kafka is their only data-plane contract. All events
for a capture use the capture ID as their Kafka key, preserving order within a
partition so `capture_complete` follows its connection logs.

Broker metadata readiness is retried for `KAFKA_STARTUP_TIMEOUT_SECONDS`; container startup does not rely solely on the broker container health status.

While consuming, broker/network errors returned by `poll()` and exceptions from
synchronous terminal-offset commits are recoverable. The service retries them
up to `KAFKA_CONSUMER_MAX_RETRIES` (default `10`) with a linear backoff based on
`KAFKA_CONSUMER_RETRY_BACKOFF_SECONDS` (default `1`). A successfully received
record starts with a fresh retry budget. Exhaustion is an infrastructure error;
malformed capture events and explicit `capture_failed` events are not retried.

The image uses Python 3.12. `pyinotify` still imports the standard-library
`asyncore` module removed in Python 3.12, so the image installs the maintained
`pyasyncore` compatibility package explicitly. Its Docker build also imports
all third-party runtime dependencies to fail immediately if the dependency set
is incomplete.
