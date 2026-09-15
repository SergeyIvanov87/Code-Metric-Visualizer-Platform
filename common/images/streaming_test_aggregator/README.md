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
