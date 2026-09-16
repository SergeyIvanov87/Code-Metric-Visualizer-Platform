# ADR 1.0: One-shot streaming test-event pipeline

- **Status:** Accepted
- **Date:** 2026-09-16
- **Scope:** `common/images/streaming_test_aggregator`
- **Related:** [Issue #103](https://github.com/SergeyIvanov87/Code-Metric-Visualizer-Platform/issues/103)

## Context

Envoy is a permanent part of the distributed system or testbed. An operator or
army controller, such as Docker Compose, starts testing containers dynamically
for one finite launch. For that launch it also starts an isolated
`tap_subscriber`, event broker, and `log_event_aggregator`.

The temporary stack captures the launch's logs, calculates how many launched
tests passed, failed, or were skipped, exposes the result to its initiator, and
terminates. A permanent, multi-run aggregation service is intentionally outside
this architecture.

## Decision

```text
permanent testbed                         one on-demand execution

test containers -----> Envoy -----> syslog-ng
                          |
                          | private Streaming Admin Tap
                          v
                   tap_subscriber
                          |
                          v
                   event broker
                          |
                          v
                log_event_aggregator
                          |
                          v
               result artifacts/status
```

1. **Envoy is permanent.** It continues proxying before, during, and after an
   execution. The controller never stops Envoy to finalize capture.
2. **The capture stack is ephemeral.** One broker, subscriber, and aggregator
   are created for one launch and removed after diagnostics and results have
   been collected.
3. **`tap_subscriber` is capture-only.** It decodes the permanent Envoy's tap
   stream and publishes ordered events; it never evaluates pytest output.
4. **The broker is execution-scoped transport.** It orders events and absorbs
   temporary broker/network outages. Kafka is the current implementation, but
   architectural names remain technology-neutral.
5. **`log_event_aggregator` is intentionally one-shot.** It consumes one
   `CAPTURE_ID`, writes results, returns an authoritative exit code, and exits.
6. **The army controller owns orchestration.** It knows which testers it
   launched and controls readiness, result collection, and teardown. The
   aggregator is not a scheduler, registry, or long-lived status service.

`streaming` describes incremental event movement. It does not imply that the
subscriber, broker, or aggregator must run permanently.

## Execution lifecycle

For each launch, the controller:

1. Generates a unique `CAPTURE_ID` and consumer group.
2. Starts the broker and aggregator.
3. Starts the subscriber and waits for its Envoy tap subscription.
4. Launches the finite, controller-known set of testing containers.
5. Waits for the subscriber's terminal event and the aggregator's result.
6. Collects exit code, result, stdout, stderr, and capture diagnostics.
7. Tears down the execution stack without disrupting Envoy or syslog-ng.

The architecture does not require `run_id`, a multi-run state machine, tester
registration, sealing APIs, heartbeat leases, or an indefinitely polling
aggregator. The execution is the lifecycle boundary and `CAPTURE_ID` identifies
it inside the temporary pipeline.

## Component boundaries

### Permanent Envoy

Envoy remains a thin proxy. Its admin interface must remain private. Starting
or stopping an execution must not terminate or globally reconfigure Envoy.

Only one active subscriber should configure a tap extension at a time.
Overlapping executions must serialize tap ownership or use independently
identifiable listeners/taps. Because Envoy outlives an execution, deployment
configuration must also isolate the launch's traffic or provide trustworthy
producer identity so unrelated logs cannot affect test counts.

### On-demand subscriber

The subscriber parses Streaming Admin Tap data, reconstructs syslog streams,
publishes ordered `connection_log` and terminal events, buffers temporary
broker failures, and exits after the capture completes or fails.

`WAIT_MSEC_BEFORE_START` bounds the wait for the first decoded log data.
`WAIT_MSEC_UNTIL_FINISH` starts only after capture activity and defines the
quiet boundary for the finite launch. Decoded tap delivery—not Envoy's
listener-wide RX counter—is the activity signal.

Quiet time is a pragmatic execution boundary, not proof that permanent Envoy
closed every connection. The controller must configure it longer than the
largest legitimate gap between its testers' logs.

### Execution-scoped broker

The broker supplies ordered hand-off, acknowledgement, retention through the
execution, and replay during temporary failures. A single-node broker is valid
for functional tests; production durability should match the required failure
policy. Results and diagnostics must be exported before ephemeral storage is
destroyed.

### One-shot aggregator

The aggregator consumes one `CAPTURE_ID` through a terminal event, retries
temporary broker failures until its activity deadline, reconstructs analysis
inputs, applies canonical pass/fail/skip rules, persists diagnostics, and exits.

Horizontal simian-army behavior comes from the controller creating separate
one-shot executions, not from multiplexing many launches in one aggregator.

## Event and failure semantics

The version-1 contract contains `connection_log`, `capture_complete`,
`capture_start_timeout`, and `capture_failed`. Every event has
`schema_version`, `capture_id`, and `type`; all records use `CAPTURE_ID` as the
partition key.

Stable event IDs remain useful for idempotent replay within one execution, but
do not require a separate `run_id` or multi-run model.

The execution fails closed when the admin stream is interrupted or malformed,
initial traffic does not arrive, buffered events cannot drain by their
deadline, the consumer cannot make progress, an event is invalid, or analysis
cannot produce a trustworthy result. Current publisher buffering survives a
broker/network outage only while the subscriber remains alive. A bounded local
WAL may be added if restart recovery is required.

## Hardening plan

These improvements preserve the one-shot architecture:

1. Publish complete syslog records incrementally.
2. Add stable event IDs and idempotent materialization.
3. Make terminal offset progression recoverable with durable result creation.
4. Bound reader, application, and producer queues by bytes and event count.
5. Optionally add a subscriber WAL for restart recovery.
6. Fault-test broker delay/loss, tap disconnection, malformed input, resource
   exhaustion, aggregator restart, and analyzer failure.
7. Define traffic isolation for overlapping launches sharing permanent Envoy.
8. Export results before destroying execution resources.

## Acceptance criteria

- Execution startup and teardown never stop permanent Envoy.
- A subscriber may start before testers and reports a distinct initial timeout.
- Events preceding `capture_complete` are delivered in order.
- Temporary broker/network outages recover within configured deadlines.
- Every terminal path produces diagnosable, authoritative status.
- Unrelated permanent-system traffic cannot be counted in the launch.
- Resource exhaustion fails explicitly rather than producing a false pass.
- The controller collects results before cleanly removing the temporary stack.

## Primary references

- [Envoy admin tap handler](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/tap_filter#admin-handler)
- [Apache Kafka design](https://kafka.apache.org/41/design/design/)
- [Apache Kafka producer configuration](https://kafka.apache.org/41/javadoc/org/apache/kafka/clients/producer/ProducerConfig.html)
