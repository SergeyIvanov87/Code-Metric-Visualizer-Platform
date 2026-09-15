# Test aggregator subscriber image

> **Status: experimental bounded-batch alternative.** This decomposition makes
> Envoy thinner, but it is not yet a session-aware replacement for the canonical
> aggregator. See [the architecture evaluation](ARCHITECTURE_EVALUATION.md).

This image keeps traffic proxying and test-result analysis in separate
containers. Envoy owns the TCP listener and forwards Docker syslog traffic to
syslog-ng. The subscriber posts an `any_match` tap configuration to Envoy's
`/tap` admin endpoint and decodes its length-delimited protobuf response as it
arrives. Only reconstructed downstream bytes are temporarily spooled per
connection; raw protobuf taps are not written unless `RETAIN_RAW_TAPS=true` is
selected for diagnostics.

Once the downstream RX-byte counter has remained unchanged for
`WAIT_MSEC_UNTIL_FINISH`, the subscriber closes the admin stream, atomically
publishes reconstructed records into `/logs/syslog-streams`, and runs the same
pytest summary aggregation algorithm as `test_aggregator_image`. Results are written
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
container checks that raw taps are omitted by default, verifies reconstructed
producer streams, and validates the final passed/skipped statistics.

## Streaming versus files

Writing the received protobuf stream to tap files is **not required** for
decoding. The subscriber parses every complete `TraceWrapper` frame directly
from the HTTP response, groups it by `trace_id`, and immediately extracts its
downstream read bytes. By default `/logs/taps` therefore remains empty.

Some state is still necessary because a TCP/syslog record can span several tap
segments and Docker logging connections can remain open after pytest exits.
The implementation uses per-connection files under the temporary
`/logs/syslog-streams/.spool` directory rather than keeping unbounded byte
arrays in RAM. At a connection-close or bounded-batch quiet boundary, it frames
those bytes into records, atomically publishes the `.log` file, and removes the
spool. This is streaming transport decoding with disk-backed connection
assembly—not a store-all-taps-then-decode pipeline.

Set `RETAIN_RAW_TAPS=true` only when exact protobuf evidence is needed for
diagnostics or replay. That option recreates length-delimited files under
`/logs/taps` while continuing to decode on receipt, and carries an intentional
storage cost.
