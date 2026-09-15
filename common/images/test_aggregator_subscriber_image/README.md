# Test aggregator subscriber image

This image keeps traffic proxying and test-result analysis in separate
containers. Envoy owns the TCP listener and forwards Docker syslog traffic to
syslog-ng. The subscriber posts an `any_match` tap configuration to Envoy's
`/tap` admin endpoint, consumes its length-delimited protobuf response, and
persists one raw trace per Envoy connection under `/logs/taps`.

Once the downstream RX-byte counter has remained unchanged for
`WAIT_MSEC_UNTIL_FINISH`, the subscriber closes the admin stream, decodes the
captured downstream bytes into `/logs/syslog-streams`, and runs the same pytest
summary aggregation algorithm as `test_aggregator_image`. Results are written
to `/logs/aggregator`.

Envoy must configure the tapped transport socket with an admin configuration
whose `config_id` equals `ENVOY_TAP_CONFIG_ID`. Its admin listener must be
reachable from the subscriber container. See
`tests/functional/envoy.yaml` for a minimal configuration.

## Functional test

From this directory, run:

```sh
docker compose -f tests/functional/compose-functional.test.yaml up \
  --build --abort-on-container-exit --exit-code-from functional-tests
```

The fixture uses the native Envoy image, a standalone syslog-ng destination,
and three small producers using Docker's syslog logging driver. The pytest
container checks raw per-connection traces, reconstructed producer streams,
and the final passed/skipped statistics.
