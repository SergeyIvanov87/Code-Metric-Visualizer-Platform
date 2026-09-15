# Evaluation: capture subscribers, durable event backbone, and test aggregator

## Executive decision

The separation is sound, with one important correction:

- rename the current component conceptually to **tap subscriber** (capture
  adapter);
- make the **test aggregator** a separate, stateful service that consumes
  durable normalized events;
- choose **Kafka as the event backbone**;
- use Elasticsearch only as an optional searchable projection, not as the
  queue or source of truth.

This is stronger than both the in-Envoy file watcher and the current combined
subscriber/aggregator image. It creates replay, independent scaling, bounded
consumer concurrency, and a natural place for the session protocol proposed in
issue #103. It does **not** remove the capture edge as a failure boundary, and
running multiple subscribers against one Envoy admin tap is not a valid HA
mechanism.

## Corrected topology

```text
                         private, local admin connection
  Envoy instance A  <------------------------------------  tap_subscriber A
       |                                                         |
       v                                                         | idempotent producer
   syslog-ng                                                     v
                                                          Kafka topic(s)
  Envoy instance B  <------------------------------------  tap_subscriber B
       |                                                         |
       v                                                         |
   syslog-ng                                                     |
                                                                v
                                     test-aggregator consumer group
                                             |          |
                                      run state/API   result store
                                             |
                                      optional Elasticsearch
                                      searchable projection
```

Use one active subscriber per Envoy tap extension. Scale by pairing subscribers
with Envoy instances or listener shards, not by attaching many subscribers to
the same admin endpoint. Envoy documents that after an HTTP/1 admin tap client
disconnects, a new tap may be impossible until Envoy detects the close. This
makes concurrent active subscribers to one tap configuration a contention
risk, not redundancy.

If two capture paths deliberately observe identical traffic, the pipeline must
expect duplicates and deduplicate by a stable event ID. If traffic is merely
load-balanced across Envoy replicas, extra subscribers improve capacity and
failure isolation but do not replicate an event: the selected Envoy/subscriber
pair is still the only capture path for that connection.

## Component responsibilities

### Tap subscriber

The subscriber is an edge adapter, not a test aggregator. It should:

1. maintain the private Envoy admin tap session;
2. validate each length-delimited protobuf frame;
3. extract transport events without interpreting pytest output;
4. attach an event envelope and schema version;
5. publish with Kafka idempotence and `acks=all`;
6. advance its local checkpoint only after broker acknowledgement;
7. expose capture gaps, reconnects, and publish failures as metrics/events.

It should not decide that a run passed, infer batch completion from global
quiet, or own the authoritative run lifecycle.

A useful event identity is:

```text
(envoy_instance_id, envoy_boot_id, tap_session_id, trace_id, segment_ordinal)
```

Envoy `trace_id` alone is insufficient as a global key. Partition connection
events by the full connection identity so Kafka preserves their order. Carry
`run_id`, `tester_id`, and `attempt` as explicit metadata as early as possible;
do not recover them solely from decoded console text.

### Test aggregator

The aggregator should:

1. consume through a Kafka consumer group;
2. assemble ordered connection/tester events idempotently;
3. maintain the issue #103 run state machine;
4. apply per-tester heartbeat leases;
5. finalize only after `seal`, terminal/expired testers, and drain grace;
6. persist a run manifest and structured result;
7. commit Kafka offsets only after the state/result transaction is durable.

Multiple aggregator instances then provide failover and partitioned scale. A
consumer group assigns a partition to one active member at a time; it does not
cause every aggregator replica to analyze the same event. Independent
consumers such as indexing, audit, and metrics use separate consumer groups.

## The capture-gap limitation

Kafka replication protects an event **after Kafka acknowledges it**. It cannot
recover tap segments that were emitted while the subscriber was disconnected
or that were read but lost before publication. Therefore “more subscribers”
does not by itself eliminate the network single point of failure.

Choose one of these policies explicitly:

- **Fail-closed bounded batch:** any tap disconnect or uncheckpointed sequence
  gap makes affected runs infrastructure-failed.
- **Local write-ahead log:** append the normalized event locally before Kafka
  publication and replay unacknowledged entries after restart. This covers
  broker/network outages after receipt, but not segments emitted while the
  admin tap is disconnected.
- **Durable capture at Envoy:** retain file-per-tap output as a fallback source
  when lossless evidence is mandatory. This weakens the “thin proxy” goal but
  is the only current design here with replay at the capture origin.
- **Duplicated traffic path:** mirror traffic into independently captured paths
  and deduplicate downstream. This is expensive and must prove that the mirror
  itself is not the common failure point.

The system must publish explicit `capture_started`, `capture_interrupted`,
`capture_resumed`, and `capture_ended` events. Absence of data is not evidence
of a healthy capture.

## Kafka versus Elasticsearch

### Decision matrix

Scores are relative for this workload: 5 is strongest.

| Requirement | Kafka | Elasticsearch | Explanation |
| --- | ---: | ---: | --- |
| Durable ordered event log | 5 | 2 | Kafka is offset-based and preserves partition order; Elasticsearch is a searchable document store. |
| Replay after consumer failure/change | 5 | 2 | Kafka consumers reset/replay offsets; Elasticsearch polling requires custom watermarks and tie-breaking. |
| Consumer groups and backpressure | 5 | 1 | Kafka natively decouples producer rate from consumers; Elasticsearch can reject or slow indexing but is not a work queue. |
| Multiple independent consumers | 5 | 3 | Kafka consumer groups independently replay; Elasticsearch clients repeatedly query shared indices. |
| Stateful aggregation input | 5 | 2 | Ordered keyed events map naturally to per-run/tester state. |
| Full-text diagnostics/search | 2 | 5 | Elasticsearch is designed for indexed search and aggregations. |
| Immediate ad-hoc operator queries | 2 | 5 | Elasticsearch provides the better investigation interface. |
| Small local-test footprint | 3 | 2 | A single KRaft broker is adequate for tests; Elasticsearch is also heavy and direct indexing still needs consumer semantics. |
| Production operational simplicity | 2 | 2 | Both are substantial distributed systems; Kafka fits the required primitive, avoiding queue emulation. |

### Why Kafka should be authoritative

This pipeline is fundamentally an ordered-event consumption problem:
subscribers produce events, aggregator replicas process each partition once at
a time, failures require replay, and slow consumers need backpressure without
losing data. Kafka directly models those requirements.

Recommended production defaults:

- at least three brokers;
- replication factor 3;
- `min.insync.replicas=2`;
- producer `acks=all` and idempotence enabled;
- keys that keep one connection, tester attempt, or run ordered as required;
- retention long enough to rebuild aggregator state and investigate failures;
- explicit dead-letter/quarantine topics for invalid schemas or undecodable
  events;
- schema compatibility enforcement (Protobuf, Avro, or JSON Schema).

A single-node KRaft broker is appropriate only for functional tests. It tests
protocol behavior, not redundancy.

Kafka's exactly-once features do not make the whole Envoy-to-result pipeline
exactly once. HTTP tap receipt is outside Kafka transactions. Consumers and
state updates must still be idempotent, event IDs must be stable, and the
capture-gap policy above remains necessary.

### Why Elasticsearch should not be the queue

Direct subscriber-to-Elasticsearch indexing looks simpler, and replica shards
provide storage redundancy, but it pushes queue semantics into application
code. The aggregator would need to poll by timestamps or sequence fields,
manage refresh visibility, establish stable pagination, persist watermarks,
handle late documents, and prevent duplicates or omissions during retries and
index rollover. A successful index acknowledgement also does not define a
run/session boundary.

Elasticsearch remains valuable downstream for:

- full-text search across captured logs;
- dashboards and failure investigation;
- cross-run trend queries;
- retention tiers for operator-visible diagnostics.

Populate it from a separate Kafka consumer or connector. If indexing is down,
Kafka retains events and test aggregation can continue; if Elasticsearch is
the source of truth, indexing health becomes part of the critical result path.

## Event model

Do not publish only free-form log lines. Use a versioned envelope such as:

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
  "kind": "transport_read",
  "payload": "base64-or-structured-data"
}
```

Separate topics are reasonable for:

- `test-capture-events` — ordered normalized transport/log events;
- `test-lifecycle-events` — register, started, heartbeat, completed, aborted,
  seal, and cancel;
- `test-capture-errors` — gaps, truncation, schema errors, and quarantined data;
- `test-results` — immutable structured run results.

Avoid a topic per run because unbounded topic cardinality becomes an
operational problem. Partition shared topics by a deliberate key and include
`run_id` in every relevant record.

## Availability and scaling semantics

| Failure | Expected behavior |
| --- | --- |
| Subscriber process fails | Supervisor restarts it; emit a capture gap; affected run cannot pass unless policy proves coverage. |
| Envoy fails | Proxy and tap both fail; route new connections to another healthy Envoy, but do not pretend an interrupted connection was recovered. |
| Kafka leader/broker fails | Producer retries; quorum replication continues when ISR policy is satisfied. |
| Aggregator replica fails | Consumer group reassigns partitions; replacement replays from committed offsets. |
| Elasticsearch fails | Search/index projection lags; capture and authoritative aggregation continue. |
| Poison event | Quarantine with event identity; apply explicit per-run infrastructure-failure policy. |

Scale subscribers with Envoy capture shards. Scale aggregators up to useful
Kafka partition concurrency. Adding replicas beyond the partition count adds
failover capacity, not processing throughput.

## Relationship to issue #103

This architecture provides the durable event substrate missing from the
current implementation, but Kafka does not itself create session semantics.
The standalone aggregator must still implement registration, per-tester
leases, terminal states, sealing, draining, cancellation, durable manifests,
and the test-versus-infrastructure failure taxonomy.

Compared with the current subscriber image, this approach improves:

- restartable/replayable downstream processing;
- horizontal aggregation and bounded consumer concurrency;
- separation of capture failures from test interpretation;
- support for structured lifecycle events and multiple projections.

It still does not solve, without additional protocol work:

- loss between Envoy and the subscriber;
- identification of a run/tester when metadata is absent;
- authoritative completion;
- resource quotas and retention;
- correctness across duplicate or reordered cross-partition events.

## Implemented bounded-batch slice

The repository now implements the first vertical slice of this split:

- `tap_subscriber` contains Envoy capture, transport decoding,
  and an idempotent Kafka producer, but no pytest analyzer;
- `log_event_aggregator` contains a Kafka consumer and an independent
  copy of the pytest analyzer;
- the version-1 bounded contract publishes `connection_log` records followed by
  `capture_complete`, or a terminal `capture_failed` infrastructure event;
- the functional topology includes a single-node Kafka broker.

This slice intentionally retains global quiet and one `CAPTURE_ID` per analyzer
run for compatibility. It is not yet the session-aware, per-segment,
recoverable implementation described above.

## Recommended rollout

1. Extract `tap_subscriber.py` into a `tap_subscriber` image and remove
   pytest aggregation from that image.
2. Define the event envelope, identity, partition key, and compatibility rules
   before selecting client libraries.
3. Add a single-node Kafka KRaft functional fixture and prove publish,
   reconnect, duplicate, ordering, and replay behavior.
4. Build the standalone aggregator with a durable state store and issue #103
   lifecycle API; make consumers idempotent before adding replicas.
5. Deploy three-broker Kafka and one subscriber per Envoy instance; enforce a
   private admin network and capture-gap alarms.
6. Add Elasticsearch later as a Kafka-fed diagnostic projection if search and
   dashboards justify its operational cost.
7. Run chaos tests for subscriber death between read/ack, Kafka quorum loss,
   consumer rebalance, poison events, late lifecycle messages, duplicate
   segments, Envoy restart, and Elasticsearch outage.

## Final estimate

**Architectural strength: materially better, provided Kafka is the source of
truth and the capture-gap limitation is treated explicitly.** The largest gain
comes from durable decoupling and replay, not from multiplying subscribers.
The proposed architecture is a strong foundation for issue #103's
session-aware service, but it should not be called highly available until the
Envoy-to-subscriber edge, idempotency, session lifecycle, and state-store
recovery are designed and tested.

## Primary references

- [Envoy admin tap handler](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/tap_filter#admin-handler)
- [Apache Kafka design: persistence, consumers, delivery, and replication](https://kafka.apache.org/41/design/design/)
- [Apache Kafka producer configuration](https://kafka.apache.org/41/javadoc/org/apache/kafka/clients/producer/ProducerConfig.html)
- [Apache Kafka KRaft operations](https://kafka.apache.org/41/operations/kraft/)
- [Elasticsearch data streams](https://www.elastic.co/docs/manage-data/data-store/data-streams)
- [Elasticsearch document replication model](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-replication.html)
