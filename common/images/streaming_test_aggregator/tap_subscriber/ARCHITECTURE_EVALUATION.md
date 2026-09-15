# Architecture evaluation: Streaming Admin Tap subscriber

> Historical evaluation of the bounded combined prototype. The implementation
> has since been split into a pure Kafka-producing tap subscriber and
> `log_event_aggregator`; see `EVENT_PIPELINE_EVALUATION.md`.

## Decision

**Adopt this image as an experimental, bounded-batch alternative; do not replace
`test_aggregator_image` with it yet.**

The subscriber is a better *deployment decomposition*: Envoy only proxies and
publishes taps, while a replaceable process owns persistence, decoding, and
pytest interpretation. It is not yet a better *execution architecture*. In
particular, it does not solve the session and lifecycle problems documented in
[issue #103](https://github.com/SergeyIvanov87/Code-Metric-Visualizer-Platform/issues/103),
and moving from file taps to a live admin stream introduces availability and
capture-boundary risks.

## What becomes stronger

| Quality | Effect | Reason |
| --- | --- | --- |
| Separation of concerns | Better | Envoy no longer contains Python, inotify, SSH helpers, aggregation code, or a writable `/logs` volume. |
| Independent evolution | Better | Capture consumption and pytest interpretation can be versioned, scaled, and replaced without rebuilding the proxy. The copied scripts intentionally avoid source coupling to the canonical image. |
| Proxy filesystem footprint | Better | Envoy does not create one local file per connection and needs no shared artifact volume. |
| Deployment flexibility | Better | The subscriber can run as a sidecar or separate service and artifacts can later move to object storage or a queue. |
| Live processing potential | Better | Length-delimited segments can eventually feed a bounded worker pipeline before a connection closes. |
| Failure blast radius | Mixed | Subscriber crashes do not stop forwarding, but they can silently leave a test run without capture unless an orchestrator monitors both services. |

## What stays unchanged

The implementation deliberately copies the canonical result parser, so its
application-level behavior and limitations remain:

- pytest outcomes are inferred from console-summary regular expressions;
- producer identity is inferred from decoded syslog text;
- TCP connections are treated as artifact identities, not tester identities;
- test failure and capture/infrastructure failure share the container result
  channel;
- there is no `run_id`, `tester_id`, attempt, registration, seal, or durable run
  manifest.

The RX-byte heartbeat is also still global. Therefore issue #103's central
finding remains true: traffic silence cannot distinguish “the batch is done”
from “the next tester has not arrived yet.” A noisy connection can keep the
whole batch alive, unrelated traffic can postpone completion, and a late wave
can arrive after the subscriber has exited.

## What becomes weaker or riskier

### 1. The Envoy admin interface is now a network dependency

The canonical image binds admin to loopback. A separate subscriber requires an
admin listener reachable across the container network. Envoy admin is a
powerful, unauthenticated operational interface; it must never be published to
the host or an untrusted network. Network policy should allow only the
subscriber and operator diagnostics to connect. Longer term, prefer a loopback
sidecar/pod arrangement or a narrowly scoped tap relay rather than exposing the
whole admin API.

### 2. One live stream is a single point of capture failure

A subscriber restart, TCP reset, Envoy restart, or admin-stream failure loses
segments emitted while disconnected. The current implementation fails closed
when the stream ends, which avoids a false pass, but it has no resume token or
replay. File-per-tap output survives watcher restarts more naturally because
completed files remain on disk.

Envoy also permits only one active admin tap configuration for a given tap
extension. Operational tooling and concurrent runs must not contend for it.

### 3. Completion is no longer a connection-close boundary

The canonical implementation stops Envoy after quiet time, waits for
`CLOSE_WRITE`, and decodes immutable files. The subscriber must not stop a
shared proxy. At quiet time it closes its HTTP subscription and decodes all
complete protobuf segments received so far, including connections that remain
open. Protobuf framing is intact, but the captured application stream is a
point-in-time prefix and can end in the middle of a syslog record. This is an
important semantic regression for long-lived Docker logging connections.

A production successor needs an explicit run seal plus drain protocol and
should retain incremental per-connection framing state. It must only finalize
records terminated by a complete syslog boundary, while retaining an
unterminated suffix until a close event or a defined drain deadline.

### 4. Resource limits moved; they did not disappear

Envoy no longer retains tap files, and the subscriber now protobuf-decodes each
segment immediately instead of duplicating the raw tap by default. It still
spools reconstructed connection bytes until a safe publication boundary, so
there is no cap on active connections, total bytes, disk use, decoder work, or
retention. Optional `RETAIN_RAW_TAPS=true` deliberately adds diagnostic storage.
`MAX_BUFFERED_RX_BYTES` limits an Envoy capture body, not total run storage.
Quotas and backpressure are required before army-of-monkeys use.

### 5. Operational coupling remains

Completion still polls the exact
`tcp.destination.downstream_cx_rx_bytes_total` stat name. Temporary admin
failure currently looks like no counter update; tap frames themselves do reset
activity, but repeated stats failures have no explicit degraded/fail-fast
policy or diagnostic threshold.

## Comparison with issue #103 acceptance criteria

| Criterion | Status | Notes |
| --- | --- | --- |
| May start before testers without finishing | Not met | Initial global quiet still ends the subscriber. |
| Staggered tester waves until sealed | Not met | There is no admission window or seal operation. |
| Independent tester heartbeat leases | Not met | Only a global Envoy RX counter exists. |
| Noisy tester cannot hide hung tester | Not met | Any RX traffic renews global activity. |
| Seal + terminal testers + drain completion | Not met | Completion is only quiet time or hard timeout. |
| Reconnect attribution | Not met | Connection ID and inferred producer are the only correlation. |
| Ignore unrelated traffic for lifecycle | Not met | All listener RX bytes affect quiet time. |
| Bounded processing/resources | Not met | No queue, quota, or retention limit exists. |
| Restart recovery | Not met | Startup clears artifacts and the admin stream has no replay. |
| Separate test/infrastructure failures | Partly met | Diagnostics differ, but both map to the same result/exit channel. |

Thus the subscriber improves **two enabling conditions** for the target design
(clean responsibility boundaries and live segment access), but directly
satisfies none of the dynamic-session acceptance criteria.

## Recommended target topology

```text
                          private admin network
Envoy TCP proxy  -------------------------------->  tap subscriber
      |                                               |
      v                                               v
  syslog-ng                                  durable bounded event queue
                                                      |
                                  +-------------------+------------------+
                                  |                                      |
                         connection assembler                    run coordinator
                                  |                       register/heartbeat/seal
                                  v                                      |
                         bounded decoder pool                            v
                                  +---------------------------> run manifest/results
```

Keep Envoy stateless and thin. Split the subscriber internally into capture,
assembly, and bounded decoding stages, and introduce the session coordinator
specified by issue #103. The coordinator—not global traffic silence—must own
finalization.

## Incremental implementation order

1. Harden bounded-batch mode: validate admin reachability continuously, count
   consecutive stats failures, preserve partial-record suffixes, add byte/file
   quotas, and make stream interruption an explicit infrastructure result.
2. Add a run manifest and API for `register`, per-tester `heartbeat`, terminal
   status, `seal`, and `cancel`; keep quiet-time mode as an opt-in compatibility
   policy.
3. Require structured `run_id`, `tester_id`, and `attempt` correlation and
   partition artifacts by those keys before decoding.
4. Replace synchronous post-capture decoding with a bounded queue and worker
   pool; add retention and backpressure.
5. Add durable state/restart recovery and structured results (JUnit or JSON).
6. Run the complete chaos matrix from issue #103 before promoting this image to
   the default aggregator.

## Promotion gates

Do not replace the canonical image until all of the following hold:

- Envoy admin is private and access-controlled by deployment policy;
- loss/restart of either side produces an attributable infrastructure failure
  and cannot yield a false pass;
- run completion uses explicit sealing and per-tester terminal state;
- partial streams and reconnects are correlated without dropping or combining
  records;
- memory, file descriptors, queue depth, capture bytes, disk, and retention are
  bounded and observable;
- fault-injection covers delayed waves, stream resets, Envoy/subscriber
  restarts, malformed/truncated frames, disk pressure, and concurrent closes.

Until then, choose by workload:

- use `test_aggregator_image` for the most conservative finite CI batch and
  immutable close-before-decode behavior;
- use `tap_subscriber` to evaluate proxy/analysis decoupling
  in a controlled finite batch;
- use neither as the final army-of-monkeys/session-aware architecture.
