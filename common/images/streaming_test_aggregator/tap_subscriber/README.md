# Envoy tap subscriber image

This image is a pure capture adapter and Kafka producer. It does not analyze
pytest output and is not the test aggregator.

It posts an `any_match` configuration to Envoy's `/tap` admin endpoint, parses
the adjacent `JSON_BODY_AS_BYTES` trace objects as they arrive, converts them
to `TraceWrapper` messages, groups
transport reads by connection, reconstructs syslog records, and publishes
`connection_log` events to Kafka. After the bounded-batch RX quiet interval it
publishes `capture_complete`. If no downstream data arrives during
`WAIT_MSEC_BEFORE_START`, it publishes `capture_start_timeout` and exits with
code `10`. Other fatal capture errors are published as `capture_failed` by
bootstrap.

The standalone analyzer is `../log_event_aggregator`. Kafka
is the only data-plane contract between the two services; neither service reads
the other's runtime filesystem.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `ENVOY_ADMIN_HOST` | `envoy` | Envoy admin host on a private network. |
| `ENVOY_ADMIN_PORT` | `9901` | Envoy admin port. |
| `ENVOY_TAP_CONFIG_ID` | `test_aggregator` | ID configured in Envoy's tap transport socket. |
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092` | Kafka bootstrap brokers. |
| `KAFKA_STARTUP_TIMEOUT_SECONDS` | `120` | Wait for usable broker metadata. |
| `KAFKA_TOPIC` | `test-capture-events` | Capture event topic. |
| `CAPTURE_ID` | `functional-test` | Bounded capture identity and Kafka record key. |
| `WAIT_MSEC_BEFORE_START` | `60000` | Maximum wait for the first downstream capture bytes. |
| `WAIT_MSEC_UNTIL_FINISH` | `15000` | RX quiet interval after capture has started. |
| `MAX_WAIT_MSEC_UNTIL_FINISH` | `900000` | Capture deadline. |
| `RETAIN_RAW_TAPS` | `false` | Retain diagnostic protobuf tap files locally. |

See [the event contract](EVENT_SCHEMA.md) and the subsystem
[architecture decision record](../EVENT_PIPELINE_ARCHITECTURE_DECISION_RECORD_v1_0.md).

## Streaming and temporary files

Raw protobuf tap files are not required. Each JSON object is decoded directly
from the HTTP response. When retention is enabled, the subscriber serializes
normalized length-delimited protobuf files after parsing; these files are not
byte-for-byte copies of the admin response. Reconstructed connection bytes are
temporarily spooled under `/logs/subscriber/streams/.spool` because TCP records
can span frames and
keeping every active stream in RAM would be unbounded. The finalized log is
published to Kafka and immediately removed. Set `RETAIN_RAW_TAPS=true` only for
diagnostics or replay experiments.
