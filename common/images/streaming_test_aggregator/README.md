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
