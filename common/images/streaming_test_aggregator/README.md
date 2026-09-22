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

The one-shot architecture, including the permanent Envoy and on-demand
execution lifecycle, is recorded in
[`EVENT_PIPELINE_ARCHITECTURE_DECISION_RECORD_v1_0.md`](EVENT_PIPELINE_ARCHITECTURE_DECISION_RECORD_v1_0.md).
A legacy-substitution verdict and configuration prerequisites are in
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

## Permanent proxy and on-demand executions

`common/images/compose-logger-subsystem.yaml` owns the permanent Envoy and
syslog-ng services. Start that project once and leave it running:

```sh
docker compose \
  -p logger-subsystem \
  -f common/images/compose-logger-subsystem.yaml \
  up --build --detach
```

The on-demand execution has two Compose entry points:

- `compose-test-aggregator-subsystem.yaml` contains the capture infrastructure:
  `proxy-ready`, Kafka, `log_event_aggregator`, and `tap_subscriber`.
- `compose-functional-tests-test-aggregator-subsystem.yaml` includes the
  capture file and adds the test producers plus the final `functional-tests`
  validation container. Compose `include` requires Docker Compose 2.20 or
  newer.

If `TEST_EXECUTION_ID` is unset, both files use `functional-test` for the
project suffix, capture ID, and consumer-group suffix. That predefined value is
suitable for a clean manual launch. Before reusing it, tear the previous
project down with `--volumes` so stale Kafka state cannot be consumed. For
repeated or controller-managed executions, export one unique ID and retain it
until result collection and teardown are complete:

```sh
export TEST_EXECUTION_ID="run-$(date -u +%Y%m%d%H%M%S)-$$"
tests_file=common/images/compose-functional-tests-test-aggregator-subsystem.yaml
```

### Start the complete execution at once

Because the functional-test file includes the capture file, this single command
starts Kafka, the proxy readiness probe, subscriber, aggregator, test producers,
and final validation container:

```sh
docker compose \
  -f "${tests_file}" \
  up --build --detach
```

Use this mode when the test producers may start as soon as the tap subscription
is healthy.

### Stage capture before starting tests

Use two commands only when capture must be established before the test scope is
introduced. Both commands must retain the same `TEST_EXECUTION_ID`; otherwise
they address different Compose projects.

```sh
capture_file=common/images/compose-test-aggregator-subsystem.yaml

# Phase 1: establish the Envoy tap subscription and wait until capture is ready.
docker compose \
  -f "${capture_file}" \
  up --build --detach --wait --wait-timeout 120

# Phase 2: reconcile the existing capture services and add the finite test scope.
docker compose \
  -f "${tests_file}" \
  up --build --detach
```

The phase-2 command does not create duplicate capture services. The matching
project name and service names cause Compose to reuse the running Kafka,
subscriber, and aggregator when their configuration is unchanged. The
`proxy-ready` one-shot probe may run again.

Start phase 2 before `WAIT_FOR_FIRST_TAP_BEFORE_FINISH_MSEC` expires.

### Collect the result and clean up

The following applies to either launch mode. The aggregator is authoritative
for capture or analysis failures. When it succeeds, `functional-tests`
provides the final validation exit code.

```sh
aggregator_id=$(docker compose \
  -f "${tests_file}" \
  ps --all --quiet log_event_aggregator)
execution_result=$(docker wait "${aggregator_id}")

if [ "${execution_result}" -eq 0 ]; then
  functional_tests_id=$(docker compose \
    -f "${tests_file}" \
    ps --all --quiet functional-tests)
  execution_result=$(docker wait "${functional_tests_id}")
fi

# Export result artifacts and diagnostics before cleanup when needed.
docker compose -f "${tests_file}" logs --no-color
docker compose \
  -f "${tests_file}" \
  down --volumes --remove-orphans

unset TEST_EXECUTION_ID
exit "${execution_result}"
```

The capture file derives the project name, `CAPTURE_ID`, and Kafka consumer
group from the same resolved ID. The functional-test file repeats the project
name and includes the capture model, so its `up`, `ps`, `logs`, and `down`
commands operate on the same execution.

Do not run overlapping executions against the same permanent Envoy tap config;
`test_aggregator` supports one active admin-tap subscriber at a time.

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
