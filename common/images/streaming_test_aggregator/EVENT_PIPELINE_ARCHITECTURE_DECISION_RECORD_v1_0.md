# ADR 1.0: Streaming test-event pipeline

- **Status:** Accepted for bounded-batch implementation; evolutionary
  architecture for simian-army execution
- **Date:** 2026-09-15
- **Scope:** `common/images/streaming_test_aggregator`
- **Related:** [Issue #103](https://github.com/SergeyIvanov87/Code-Metric-Visualizer-Platform/issues/103)

## Context

Functional-test containers send pytest-like console output through Docker's
syslog driver. Envoy proxies that TCP traffic to syslog-ng and exposes captured
transport events through Streaming Admin Tap. Capture, durable transport, and
test analysis have different scaling, availability, and lifecycle concerns and
must therefore be independent components.

The subsystem must initially preserve bounded CI-batch behavior while providing
an evolution path toward the simian-army pattern: an open service into which
testers may appear, disappear, reconnect, and arrive in staggered waves.

## Decision

Adopt an event-driven pipeline with these responsibilities:

1. **Envoy** proxies traffic and exposes a private admin tap.
2. **`tap_subscriber`** validates and decodes tap frames, reconstructs
   connection records, and publishes versioned events to a durable event
   broker. It never evaluates pytest results.
3. **The event broker** is the durable hand-off, ordering, replay, and
   backpressure boundary. The current implementation uses Kafka, but component
   and contract names remain technology-neutral.
4. **`log_event_aggregator`** consumes events, reconstructs analysis inputs, and
   applies the test-result algorithm. In the bounded implementation it handles
   one `CAPTURE_ID`; its target form is a long-running, multi-run service.
5. **An optional searchable projection** may index events and results for
   diagnostics. It is not the authoritative queue or run-state store.

```text
Docker syslog producers
          |
          v
      Envoy proxy --------------------------> syslog-ng
          |
          | private Streaming Admin Tap
          v
    tap_subscriber
          |
          | versioned ordered events
          v
   durable event broker
          |
          +-----------------------> optional search/index projection
          |
          v
 log_event_aggregator instances
          |
          +----> durable run state and structured results
          +----> status/control API
```

## Why the subsystem is called “streaming”

`streaming` describes continuous event movement and incremental processing. It
is an architectural term rather than a broker product name. The name remains
valid if the broker implementation or storage projection changes.

## Component architecture

### Envoy boundary

Envoy remains a thin proxy. Its admin endpoint must be reachable only by the
paired tap subscriber and trusted operators. It must not be published on a
host-facing or untrusted network because the admin API is a powerful
operational interface.

Use one active subscriber per Envoy tap extension. Scale capture by pairing
subscribers with Envoy instances or listener shards. Attaching multiple active
subscribers to one admin tap is not an availability mechanism and may cause tap
configuration contention.

### Tap subscriber

The subscriber is a capture adapter and event producer. It is responsible for:

- maintaining the private admin tap request;
- parsing Envoy's adjacent `JSON_BODY_AS_BYTES` streaming-admin objects and
  converting them to `TraceWrapper` messages;
- rejecting malformed or truncated capture data;
- grouping downstream reads by connection identity;
- reconstructing complete syslog records without interpreting their pytest
  meaning;
- publishing a versioned event envelope;
- waiting for broker acknowledgement before advancing durable progress;
- exposing connection state, capture gaps, reconnects, and publish failures.

The bounded implementation emits reconstructed connection logs. The target
simian-army implementation should emit smaller incremental records so a
long-lived connection does not delay every record until connection closure.
It must preserve incomplete syslog suffixes across tap segments and publish only
complete records.

A globally meaningful capture identity should include:

```text
(envoy_instance_id, envoy_boot_id, tap_session_id, trace_id, segment_ordinal)
```

Envoy `trace_id` alone is not a global identifier. Every event also needs a
stable `event_id` for idempotent replay and deduplication.

### Event broker

The broker is authoritative for accepted capture and lifecycle events. It must
provide:

- durable replicated storage;
- ordering within a deliberate partition key;
- consumer offsets and replay;
- backpressure between producers and consumers;
- independent consumer groups for analysis, indexing, audit, and metrics;
- retention long enough to rebuild aggregator state.

The current Kafka deployment should use, in production:

- at least three brokers;
- replication factor 3;
- `min.insync.replicas=2`;
- producer `acks=all` and idempotence;
- schema compatibility enforcement;
- quarantine/dead-letter topics for invalid events;
- encryption, authenticated clients, and least-privilege topic ACLs.

A single-node KRaft broker is appropriate for functional testing only. It tests
protocol integration, not redundancy.

### Log event aggregator

The aggregator owns test semantics. It is responsible for:

- polling the event broker continuously;
- validating schemas and processing events idempotently;
- assembling ordered records into tester attempts and runs;
- parsing structured results or, during compatibility mode, pytest console
  summaries;
- maintaining durable run state;
- distinguishing test failures from capture/infrastructure failures;
- producing immutable structured results;
- exposing run status through an API;
- committing consumer progress only after state transitions are durable.

The current implementation is a one-shot bounded consumer: it waits for one
`CAPTURE_ID`, receives `connection_log` events through `capture_complete`, runs
analysis, and exits. The target service must keep polling across many runs and
must not treat temporary broker idleness as run completion.

Consumer-group replicas provide failover and partitioned scale. One partition
is assigned to one active group member at a time. Adding replicas beyond the
partition count adds standby capacity rather than throughput. Independent
indexing or audit processors use separate consumer groups.

### Run coordinator and state store

Full simian-army support requires an explicit coordinator, logically part of or
adjacent to `log_event_aggregator`. Model each run as:

```text
WAITING/ARMED -> ACTIVE -> SEALED/DRAINING -> FINALIZING -> COMPLETE
                                    |                         |
                                    +--------> CANCELLED <----+
```

The coordinator must support:

- `register(run_id, tester_id, attempt, heartbeat_ttl)`;
- tester `started`, `heartbeat`, `completed`, and `aborted` events;
- run `seal` and `cancel` operations;
- idempotent duplicate/replay handling;
- independent leases for every tester;
- a drain grace period after all admitted testers become terminal;
- durable manifests that survive aggregator restarts.

A run completes only when it is sealed, every registered tester is terminal or
lease-expired, and drain grace has elapsed. Global traffic silence and an empty
broker poll are never authoritative completion signals.

## Event contract

Every record has a versioned envelope. A target envelope is:

```json
{
  "schema_version": 1,
  "event_id": "envoy-a/boot-42/tap-7/trace-19/segment-3",
  "captured_at": "2026-09-15T12:00:00.123Z",
  "envoy_instance_id": "envoy-a",
  "envoy_boot_id": "boot-42",
  "tap_session_id": "tap-7",
  "trace_id": 19,
  "segment_ordinal": 3,
  "run_id": "run-123",
  "tester_id": "cc-functional-tester",
  "attempt": 1,
  "type": "transport_read",
  "payload": "base64-or-structured-data"
}
```

The bounded version-1 slice currently defines `connection_log`,
`capture_complete`, `capture_start_timeout`, and `capture_failed`. Its concrete
contract is documented in `tap_subscriber/EVENT_SCHEMA.md`.

Two timing phases are intentionally separate. `WAIT_MSEC_BEFORE_START` is the
admission interval between establishing the admin subscription and receiving
the first downstream capture bytes. Expiry emits `capture_start_timeout` and
produces exit code `10`, identifying an orchestration/startup failure rather
than an empty successful run. Only after capture begins does
`WAIT_MSEC_UNTIL_FINISH` measure inactivity. This separation lets a subscriber
become ready well before test containers start without prematurely applying the
post-start heartbeat timeout.

Recommended shared event streams are:

- `test-capture-events` for normalized transport/log events;
- `test-lifecycle-events` for registration, heartbeats, terminal states, seal,
  and cancel;
- `test-capture-errors` for gaps, truncation, invalid schemas, and quarantined
  events;
- `test-results` for immutable structured run results.

Do not create a topic per run. Partition shared topics by a key that keeps all
events requiring strict order together. Include `run_id`, `tester_id`, and
`attempt` in the event instead of deriving identity from console text.

## Delivery and consistency semantics

Broker acknowledgement protects an event only after it has reached the broker.
It cannot recover tap segments emitted while the subscriber is disconnected or
read data lost before publication. The Envoy-to-subscriber edge therefore
remains an explicit capture boundary.

The bounded implementation subscribes to Envoy without waiting for Kafka. It
uses librdkafka's ordered, non-expiring producer queue during retriable broker
and network outages and adds an application queue when that local producer
queue is full. It retries the application queue before processing each next tap
object and drains both queues on normal completion, initialization timeout, and
capture failure. The final drain has a configured deadline and fails closed if
Kafka does not recover. This protects a live process from transient outages;
it does not survive subscriber/container loss. The target architecture must
replace the application memory queue with the local write-ahead log described
below.

Each deployment must choose a capture-gap policy:

1. **Fail closed:** any unaccounted tap interruption makes affected runs
   infrastructure-failed.
2. **Local write-ahead log:** persist normalized events before publication and
   replay unacknowledged entries after restart. This covers broker outages after
   receipt, not data emitted during tap disconnection.
3. **Durable origin capture:** retain Envoy file taps as a fallback when
   lossless evidence is mandatory.
4. **Duplicated traffic path:** mirror traffic through independent capture
   paths and deduplicate with stable event IDs.

Publish explicit `capture_started`, `capture_interrupted`, `capture_resumed`,
and `capture_ended` events. Absence of events is not proof that capture is
healthy.

Exactly-once broker features do not make the entire Envoy-to-result path exactly
once because admin-tap receipt is outside broker transactions. Producers need
stable event IDs; consumers and state transitions must be idempotent; offsets
must advance only after durable effects.

## Failure behavior

| Failure | Required behavior |
| --- | --- |
| Subscriber exits | Restart it, emit a capture gap, and prevent false success for affected runs. |
| Envoy exits | Route new traffic elsewhere; mark interrupted connections rather than pretending they resumed. |
| Broker node fails | Retry publication and continue only while the configured replication quorum is satisfied. |
| Aggregator replica exits | Reassign partitions and replay from committed offsets. |
| Search projection fails | Allow indexing to lag without blocking authoritative capture or analysis. |
| Invalid event | Quarantine it with identity and attribute an infrastructure failure to the affected run/tester. |
| State store fails | Stop committing offsets until durable state is available. |
| Disk or quota is exhausted | Apply backpressure or fail explicitly; never drop evidence and report success. |

## Resource boundaries

Before unrestricted simian-army use, configure and observe limits for:

- active Envoy connections and tap sessions;
- subscriber spool bytes and file descriptors;
- event size and producer queue depth;
- broker partition count, retention bytes, and consumer lag;
- active runs, testers per run, and attempts per tester;
- aggregation worker concurrency and state-store size;
- raw evidence, decoded records, results, and search-index retention.

Capacity failures must identify the effective limit and a remediation action.
Backpressure is preferable to unbounded memory or disk growth.

## Security

- Keep Envoy admin on a private network and restrict it to the paired subscriber.
- Authenticate and encrypt broker traffic.
- Give subscribers produce-only access to capture/error streams.
- Give aggregators consume access to inputs and produce access to results.
- Authenticate register, seal, cancel, and status APIs with scoped run tokens.
- Treat captured logs as potentially sensitive and apply retention and access
  policies consistently across broker, state store, and search projection.

## Observability

Expose metrics and structured diagnostics for:

- tap connection state and reconnect count;
- capture gaps, malformed frames, and truncations;
- published, retried, failed, and queued events;
- broker acknowledgement latency and consumer lag;
- active/sealed/completed/cancelled runs;
- registered, active, completed, aborted, and expired testers;
- deduplicated/replayed events;
- aggregation latency and parser failures;
- spool, broker, state-store, and projection storage usage.

Correlate every log and metric with `run_id`, `tester_id`, `attempt`, capture
identity, and event ID where applicable.

## Evolution plan toward full simian-army support

### Phase 1 — bounded event pipeline (implemented)

- Separate tap capture from pytest analysis.
- Publish versioned connection logs and terminal capture events.
- Consume one capture through an explicit completion marker.
- Exercise the topology with a single-node functional broker.

### Phase 2 — durable identities and incremental records

- Add `event_id`, Envoy boot/session identity, segment ordinal, `run_id`,
  `tester_id`, and `attempt`.
- Publish complete syslog records incrementally rather than waiting for a
  connection-level artifact.
- Add a local WAL or explicitly fail closed across every capture gap.
- Enforce schemas and add error/quarantine streams.

### Phase 3 — long-running multi-run aggregator

- Replace one-shot `CAPTURE_ID` filtering with an indefinite consumer loop.
- Maintain many run state machines concurrently.
- Add bounded worker pools and partition-aware ownership.
- Persist run state and consumer progress durably and idempotently.
- Publish structured result events instead of representing a run result through
  the service process exit code.

### Phase 4 — explicit tester lifecycle

- Implement registration, per-tester heartbeat leases, terminal events, seal,
  cancel, and drain grace.
- Reject or quarantine unregistered traffic so it cannot extend run lifetime.
- Correlate reconnects and multiple connections with the correct tester
  attempt.
- Separate test, capture, timeout, capacity, and control-plane failures.

### Phase 5 — production resilience

- Deploy a replicated broker and durable state store.
- Add quotas, retention, backpressure, authentication, authorization, and
  encryption.
- Add an optional broker-fed search projection.
- Validate restart recovery and state rebuild from retained events.

### Phase 6 — chaos qualification

Exercise at least:

- subscriber injection before any tester;
- long and repeated inter-arrival gaps;
- staggered tester waves before sealing;
- one missed heartbeat while other testers remain noisy;
- tester reconnect and container recreation;
- duplicate and replayed events;
- subscriber death before and after broker acknowledgement;
- Envoy restart and admin-stream interruption;
- broker quorum loss and consumer rebalance;
- malformed/truncated frames and poison events;
- simultaneous closure of many connections;
- disk pressure, quota exhaustion, and oversized captures;
- aggregator and state-store restart;
- seal/cancel while testers are active;
- search-projection outage.

## Consequences

### Benefits

- Envoy remains focused on proxying.
- Capture and analysis scale and deploy independently.
- Accepted events are replayable and can feed multiple consumers.
- The architecture has a clear location for durable session state and explicit
  tester lifecycle.
- Search/indexing failures do not need to block authoritative aggregation.

### Costs and constraints

- The broker and state store add operational complexity.
- The capture edge still needs an explicit loss policy.
- Schema evolution, ordering keys, idempotency, quotas, and retention become
  first-class design responsibilities.
- The bounded implementation is not yet a continuously running simian-army
  service.

## Promotion criteria

The subsystem supports the full simian-army pattern only when:

- it may start before testers without finalizing due to initial silence;
- testers may join in staggered waves until the run is sealed;
- every tester has an independent heartbeat lease;
- noisy traffic cannot hide a dead tester;
- reconnects map to the correct tester attempt;
- unregistered traffic cannot affect completion;
- run state and offsets recover after restart without loss or double counting;
- capture gaps cannot yield a false pass;
- processing and storage remain bounded under configured capacity;
- test and infrastructure failures are reported separately;
- the complete chaos matrix passes.

## Primary references

- [Envoy admin tap handler](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/tap_filter#admin-handler)
- [Apache Kafka design](https://kafka.apache.org/41/design/design/)
- [Apache Kafka producer configuration](https://kafka.apache.org/41/javadoc/org/apache/kafka/clients/producer/ProducerConfig.html)
- [Apache Kafka KRaft operations](https://kafka.apache.org/41/operations/kraft/)
