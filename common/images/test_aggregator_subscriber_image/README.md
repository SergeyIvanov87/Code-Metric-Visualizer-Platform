# Envoy tap subscriber image

This image is a pure capture adapter and Kafka producer. It does not analyze
pytest output and is not the test aggregator.

It posts an `any_match` configuration to Envoy's `/tap` admin endpoint, decodes
length-delimited `TraceWrapper` protobuf messages as they arrive, groups
transport reads by connection, reconstructs syslog records, and publishes
`connection_log` events to Kafka. After the bounded-batch RX quiet interval it
publishes `capture_complete`. Fatal capture errors are published as
`capture_failed` by bootstrap.

The standalone analyzer is `common/images/test_aggregator_kafka_image`. Kafka
is the only data-plane contract between the two services; neither service reads
the other's runtime filesystem.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `ENVOY_ADMIN_HOST` | `envoy` | Envoy admin host on a private network. |
| `ENVOY_ADMIN_PORT` | `9901` | Envoy admin port. |
| `ENVOY_TAP_CONFIG_ID` | `test_aggregator` | ID configured in Envoy's tap transport socket. |
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092` | Kafka bootstrap brokers. |
| `KAFKA_TOPIC` | `test-capture-events` | Capture event topic. |
| `CAPTURE_ID` | `functional-test` | Bounded capture identity and Kafka record key. |
| `WAIT_MSEC_UNTIL_FINISH` | `15000` | Global RX quiet interval for compatibility mode. |
| `MAX_WAIT_MSEC_UNTIL_FINISH` | `900000` | Capture deadline. |
| `RETAIN_RAW_TAPS` | `false` | Retain diagnostic protobuf tap files locally. |

See [the Kafka event contract](KAFKA_EVENT_SCHEMA.md), the
[architecture evaluation](ARCHITECTURE_EVALUATION.md), and the
[event-pipeline evaluation](EVENT_PIPELINE_EVALUATION.md).

## Streaming and temporary files

Raw protobuf tap files are not required. Each frame is decoded directly from
the HTTP response. Reconstructed connection bytes are temporarily spooled
under `/logs/subscriber/streams/.spool` because TCP records can span frames and
keeping every active stream in RAM would be unbounded. The finalized log is
published to Kafka and immediately removed. Set `RETAIN_RAW_TAPS=true` only for
diagnostics or replay experiments.

## Functional test

```sh
docker compose -f tests/functional/compose-functional.test.yaml up \
  --build --abort-on-container-exit --exit-code-from functional-tests
```

The fixture starts a single-node Kafka KRaft broker, native Envoy, syslog-ng,
three Docker syslog producers, this tap subscriber, the standalone Kafka test
aggregator, and a pytest assertion container.
