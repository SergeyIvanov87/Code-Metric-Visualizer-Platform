# Streaming test aggregator

`streaming` describes the architecture: capture events flow continuously from
the proxy-facing adapter to an event broker and then to an independent
analyzer. It is a technology-neutral architectural term, not a product name.
It also avoids the misleading implication that the proxy subscriber itself
aggregates test results.

The subsystem contains two images:

- `tap_subscriber` — subscribes to Envoy's Streaming Admin Tap, decodes capture
  frames, and publishes normalized log events;
- `log_event_aggregator` — consumes log events and applies the test-result
  analysis algorithm.

The names describe responsibilities rather than the current event-broker
implementation, allowing the transport to evolve without renaming the images.

## Documentation and functional tests

The architecture and simian-army evolution plan are recorded in
[`EVENT_PIPELINE_ARCHITECTURE_DECISION_RECORD_v1_0.md`](EVENT_PIPELINE_ARCHITECTURE_DECISION_RECORD_v1_0.md).
A bounded-batch compatibility verdict and migration prerequisites are in
[`LEGACY_SUBSTITUTION_ASSESSMENT.md`](LEGACY_SUBSTITUTION_ASSESSMENT.md).
The complete subsystem test topology lives in `tests/functional` rather than
inside either component. Run it from this directory with:

```sh
compose_file=tests/functional/compose-functional.test.yaml
docker compose -f "${compose_file}" up --build --detach
functional_tests_id=$(docker compose -f "${compose_file}" ps --all --quiet functional-tests)
docker wait "${functional_tests_id}"
docker compose -f "${compose_file}" down --volumes
```

The dedicated GitHub Actions workflow uses the same detached orchestration,
propagates the functional-test container's exit code, and prints all service
logs before cleanup.

## Broker readiness

The functional broker healthcheck creates and describes `test-capture-events`;
a TCP listener alone is not considered ready. The `log_event_aggregator`
retries metadata discovery through the advertised listener. The
`tap_subscriber` deliberately does not wait for broker readiness: it attaches
to Envoy immediately and buffers ordered events until Kafka becomes available.
This prevents broker startup or a temporary network partition from creating a
gap in tap capture.

## Functional fixture readiness

The functional topology distinguishes process startup from service readiness.
Its broker healthcheck creates and describes the capture topic, and an
`envoy-ready` probe must receive HTTP 200 from Envoy's `/ready` admin endpoint
before `tap_subscriber` starts. The fixture pins a released Envoy image.

Envoy's streaming admin sink accepts only JSON output formats. The subscriber
therefore requests `JSON_BODY_AS_BYTES`; requesting
`PROTO_BINARY_LENGTH_DELIMITED` makes Envoy reject the invalid sink invariant
and terminate, after which subscriber connection attempts can misleadingly
appear as DNS or readiness failures.

Messages such as `Coordinator load in progress` from an idempotent producer are
normally transient during single-node broker initialization. In contrast,
Envoy termination, connection refusal on the published syslog port, and
subsequent failure to resolve/reach the `envoy` service indicate that the proxy
capture path failed before any event could be produced. The aggregator then
exits only because it never receives a terminal capture event before its safety
deadline.
