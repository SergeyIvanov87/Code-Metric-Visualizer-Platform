# Legacy test aggregator substitution assessment

## Verdict

The streaming subsystem can substitute the legacy `test_aggregator_image` for
a **known, finite, bounded CI batch** when the surrounding Compose/CI topology
is deliberately reconfigured. It is **not a drop-in replacement**, and it is
not yet the preferred replacement for open-ended or simian-army execution.

Confidence by goal:

| Goal | Assessment |
| --- | --- |
| Preserve current pytest pass/fail/skip interpretation | High |
| Replace the legacy component in one isolated finite Compose run | Medium, after the prerequisites below are enforced |
| Provide equivalent operational simplicity | Low |
| Provide equivalent immutable capture boundary | Medium-low |
| Improve replay after broker acknowledgement | High with a replicated broker |
| Guarantee lossless capture across subscriber/admin failure | Low |
| Support concurrent or open-ended simian-army runs | Not yet supported |

## Functional equivalence

The result algorithm itself is equivalent: `log_event_aggregator` owns an
independent copy of the legacy `log_aggregator.py` and invokes it through the
same `log_watcher_service.sh` contract. Given the same complete reconstructed
syslog records, it calculates the same totals and applies the same pass,
failed, skipped, inconsistent-total, and no-tests policies.

The streaming data path provides the required bounded-batch sequence:

```text
Docker syslog -> Envoy -> tap_subscriber -> event broker
                                      connection_log ...
                                      capture_complete
                                               |
                                               v
                                  log_event_aggregator
                                               |
                                  canonical result analyzer
```

`capture_complete` is the positive boundary used by the consumer; an empty
broker poll is never interpreted as completion. `capture_start_timeout` is a
distinguishable initialization failure, while other capture failures remain
infrastructure failures.

## Why it is not drop-in

The legacy image provides several roles in one container:

- the externally addressed syslog TCP listener;
- Envoy proxying and tap creation;
- capture lifecycle and inactivity detection;
- decoding and pytest analysis;
- the health dependency used to start tester containers;
- the final container exit status consumed by CI.

The streaming subsystem distributes those roles across Envoy,
`tap_subscriber`, the event broker, and `log_event_aggregator`. Existing Compose
files cannot merely replace an image name. They must change service
references, readiness dependencies, networking, volumes, and which container's
exit code is authoritative.

In the streaming topology:

- test containers send syslog to the standalone Envoy listener;
- test containers wait for `tap_subscriber` readiness before starting;
- `tap_subscriber` waits for both the broker and the admin tap;
- CI waits for and uses the exit code from `log_event_aggregator`;
- result files come from the aggregator volume, not the subscriber status path.

## Required configuration for bounded substitution

All of the following are prerequisites:

1. **Unique capture identity.** Use a new `CAPTURE_ID` for every batch. Reusing
   an ID with retained events and `auto.offset.reset=earliest` can expose the
   consumer to an earlier terminal marker.
2. **Isolated consumption.** Use a dedicated consumer group for the batch. The
   current one-shot consumer filters one capture and must not share a group
   that is concurrently responsible for other captures.
3. **Ordered event key.** Keep every event for the capture keyed by the same
   `CAPTURE_ID`, so connection logs precede its terminal marker in one
   partition.
4. **Timeout relationship.** Configure
   `MAX_WAIT_MSEC_UNTIL_FINISH >= WAIT_MSEC_BEFORE_START` and ensure the
   aggregator's `MAX_WAIT_SECONDS` exceeds the subscriber's complete startup
   and capture deadline.
5. **Readiness ordering.** Start the broker and `log_event_aggregator`, establish
   the Envoy tap through `tap_subscriber`, and only then start log producers.
6. **Authoritative exit.** Use `log_event_aggregator`—not `tap_subscriber`—as the
   Compose/CI `exit-code-from` service.
7. **Private Envoy admin.** Make the admin endpoint reachable by the subscriber
   without publishing it to an untrusted or host-facing network.
8. **Production broker durability.** Replace the functional single-node broker
   with a replicated deployment and enforce producer acknowledgement,
   idempotence, retention, authentication, and authorization.
9. **Artifact persistence.** Persist `/logs/aggregator` from
   `log_event_aggregator` wherever existing CI expects result, stdout, and
   stderr artifacts.
10. **Failure monitoring.** Treat subscriber exit, `capture_start_timeout`,
    `capture_failed`, broker delivery failure, consumer timeout, and analyzer
    failure as non-successful infrastructure/test outcomes as appropriate.

## Behavioral differences that remain

### Capture finalization

The legacy implementation stops its colocated Envoy after the quiet interval
and decodes only after tap files close. This gives it an immutable
connection-close boundary. The streaming subscriber must not stop a shared
standalone Envoy; at quiet time it finalizes complete protobuf segments received
so far for connections that may still be open.

This is adequate for controlled batches whose final pytest records have arrived
before the quiet interval, but it is not identical. A late record or a syslog
record split across the chosen quiet boundary can be absent from the batch.
Before default replacement, incremental complete-record publication plus an
explicit seal/drain protocol should replace this point-in-time boundary.

### Additional infrastructure

The event broker improves durable hand-off and replay after acknowledgement,
but adds deployment, capacity, security, retention, and monitoring work. It
cannot replay bytes Envoy emitted while the admin subscriber was disconnected.
A capture gap must remain fail-closed or be covered by an explicit WAL,
origin-file fallback, or independently duplicated capture path.

### Error artifacts

Initialization timeout has a specific event, result diagnostic, and exit code
`10`. Generic consumer and capture exceptions still converge on generic process
failure paths and do not yet have the complete structured failure taxonomy
required for operational parity.

### Concurrent batches

The current consumer handles one configured `CAPTURE_ID` and exits. It is safe
for an isolated bounded run, but not a multi-run daemon. Sharing topics is
possible only with deliberate unique keys/groups and retention discipline; the
target design should instead maintain many run states continuously.

## Promotion blockers

Do not remove the legacy image or make the streaming subsystem the default
until these blockers are resolved:

- add an end-to-end functional test that runs in the project CI environment;
- add failure-path functional tests for initialization timeout, tap disconnect,
  broker outage, malformed data, and analyzer failure;
- publish complete records incrementally and preserve partial suffix state;
- introduce stable event IDs and idempotent consumer state;
- make capture gaps explicit and impossible to interpret as success;
- guarantee result artifacts for every terminal infrastructure failure;
- add resource quotas, backpressure, retention, and operational metrics;
- implement explicit run sealing and drain semantics;
- demonstrate restart/replay behavior without stale-terminal or double-count
  errors.

## Recommendation

Use the streaming subsystem as an **opt-in replacement for isolated bounded
functional-test batches** after satisfying the configuration checklist. Keep
`test_aggregator_image` available as the conservative default until CI proves
normal and failure-path parity and the immutable-boundary gap is addressed.

For simian-army execution, neither implementation is sufficient today. Evolve
`log_event_aggregator` into the long-running session-aware coordinator described
in `EVENT_PIPELINE_ARCHITECTURE_DECISION_RECORD_v1_0.md` rather than extending
global quiet-time heuristics.
