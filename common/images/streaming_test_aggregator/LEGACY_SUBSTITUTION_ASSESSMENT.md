# Legacy test aggregator substitution assessment

## Verdict

The streaming subsystem is intentionally a **one-shot substitute** for one
finite execution. This includes simian-army launches where a Docker Compose
controller dynamically starts multiple testing containers against an already
running distributed system.

Envoy is permanent. For every launch, the operator/controller starts a fresh
subscriber, broker, and aggregator, collects the aggregator's status and
artifacts, and tears those temporary components down.

The subsystem can replace the legacy aggregator for that lifecycle after the
conditions below are satisfied. It is not an image-name-only replacement,
because the legacy image colocates roles that this design separates.

## Intended topology

```text
permanent:  testers -> Envoy -> syslog-ng
                          |
on demand:                +-> tap_subscriber -> broker
                                                   |
                                                   v
                                          log_event_aggregator
                                                   |
                                                   v
                                           status and artifacts
```

The controller owns tester lifecycle. The aggregator needs neither multi-run
operation nor a separate `run_id`: one `CAPTURE_ID`, terminal event, and process
exit describe one launch.

## Required configuration

1. Use a unique `CAPTURE_ID` and consumer group for every execution.
2. Key every execution event by that `CAPTURE_ID`.
3. Start broker and aggregator, establish the tap subscription, then launch
   testers.
4. Configure `WAIT_FOR_FIRST_TAP_BEFORE_FINISH_MSEC` for the longest intended
   startup delay.
5. Configure `WAIT_FOR_NEXT_TAP_BEFORE_FINISH_MSEC` beyond the longest
   legitimate log gap, and the aggregator deadline beyond the subscriber's
   capture/drain window.
6. Treat `log_event_aggregator` as the authoritative exit-status service.
7. Collect `/logs/aggregator` before teardown.
8. Keep the permanent Envoy admin interface private.
9. Isolate the launch's traffic from unrelated permanent-system traffic.
10. Serialize tap ownership or provide independent tap/listener instances for
    overlapping executions.

## Remaining risks

- Unlike the legacy image, the subscriber must not stop permanent Envoy to
  obtain an immutable connection-close boundary. Quiet time must cover the
  launch pattern; incremental record publication can reduce this risk.
- Broker history disappears on teardown unless artifacts are exported, and it
  cannot recover traffic emitted while no subscriber was attached.
- Current publisher buffering survives broker/network interruption only while
  the subscriber process remains alive. Stable event IDs and a bounded WAL can
  provide restart recovery when required.
- A shared listener may observe unrelated traffic. Network/listener isolation
  or trustworthy producer identity must prevent incorrect test counts.

## Promotion conditions

Make this the default one-shot path after success and failure workflows run
consistently in CI; broker outage, tap disconnect, malformed data, and analyzer
failure are fault-tested; terminal result creation is crash-safe; queues are
bounded; traffic is attributable; and artifacts are exported before teardown.

Retain the one-shot model. Do not add a permanent multi-run aggregator, run
registry, sealing API, heartbeat leases, or status service unless a future
requirement changes the controller-owned execution boundary.
