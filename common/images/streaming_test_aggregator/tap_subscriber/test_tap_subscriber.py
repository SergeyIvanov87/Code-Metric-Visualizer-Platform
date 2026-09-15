import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("envoy.data.tap.v3.wrapper_pb2")
json_format = pytest.importorskip("google.protobuf.json_format")
MODULE_PATH = Path(__file__).with_name("tap_subscriber.py")
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("tap_subscriber", MODULE_PATH)
tap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tap)


def test_encode_varint_boundaries():
    assert tap.encode_varint(0) == b"\x00"
    assert tap.encode_varint(127) == b"\x7f"
    assert tap.encode_varint(128) == bytes([0x80, 0x01])
    assert tap.encode_varint(0xFFFFFFFF) == bytes([0xff, 0xff, 0xff, 0xff, 0x0f])


def test_reads_adjacent_streaming_admin_json_traces():
    first = tap.wrapper_pb2.TraceWrapper()
    first.socket_streamed_trace_segment.trace_id = 7
    first.socket_streamed_trace_segment.event.closed.SetInParent()
    second = tap.wrapper_pb2.TraceWrapper()
    second.socket_streamed_trace_segment.trace_id = 8
    second.socket_streamed_trace_segment.event.closed.SetInParent()
    first_json = json.loads(json_format.MessageToJson(first))
    first_json["socketStreamedTraceSegment"]["event"]["seqNum"] = "0"
    response = io.BytesIO(
        (
            json.dumps(first_json)
            + json_format.MessageToJson(second)
        ).encode()
    )
    reader = tap.StreamingJsonTraceReader(response)

    assert tap.trace_id_and_closed(reader.read()) == (7, True)
    # The second object was returned by the same underlying response read. It
    # must be drained without waiting for the socket to become readable again.
    assert tap.trace_id_and_closed(reader.pop_buffered()) == (8, True)
    assert reader.read() is None


def test_rejects_truncated_streaming_admin_json():
    reader = tap.StreamingJsonTraceReader(io.BytesIO(b'{"socketStreamedTraceSegment":'))

    with pytest.raises(ValueError, match="truncated tap JSON"):
        reader.read()


def test_trace_id_and_closed_for_streamed_event():
    trace = tap.wrapper_pb2.TraceWrapper()
    segment = trace.socket_streamed_trace_segment
    segment.trace_id = 42
    segment.event.closed.SetInParent()
    assert tap.trace_id_and_closed(trace) == (42, True)


def test_trace_id_rejects_buffered_trace():
    trace = tap.wrapper_pb2.TraceWrapper()
    trace.socket_buffered_trace.SetInParent()
    with pytest.raises(ValueError, match="non-streamed"):
        tap.trace_id_and_closed(trace)


def test_decodes_streamed_rx_bytes_without_a_raw_tap_file(tmp_path):
    trace = tap.wrapper_pb2.TraceWrapper()
    segment = trace.socket_streamed_trace_segment
    segment.trace_id = 7
    segment.event.read.data.as_bytes = (
        b"<14>Sep 15 12:00:00 example-tester[1]: collected 1 item"
    )
    spool = tmp_path / "connection_7.stream"

    received_data = tap.append_received_data(trace, spool)

    assert received_data
    assert spool.read_bytes().endswith(b"collected 1 item")
    assert not list(tmp_path.glob("*.pb"))


def test_reports_no_activity_for_trace_without_downstream_data(tmp_path):
    trace = tap.wrapper_pb2.TraceWrapper()
    segment = trace.socket_streamed_trace_segment
    segment.trace_id = 8
    segment.event.closed.SetInParent()

    assert not tap.append_received_data(trace, tmp_path / "connection_8.stream")


def test_finalizes_reconstructed_stream_atomically(tmp_path):
    spool = tmp_path / "connection_7.stream"
    spool.write_bytes(
        b"<14>Sep 15 12:00:00 example-tester[1]: collected 1 item"
    )

    output = tap.finalize_stream(spool, tmp_path / "connection_7.log")

    assert output.name == "example-tester__connection_7.log"
    assert output.read_bytes().endswith(b"collected 1 item\n")
    assert not spool.exists()


class FakeProducer:
    def __init__(self):
        self.records = []
        self.polls = []

    def produce(self, topic, **kwargs):
        self.records.append((topic, kwargs))

    def poll(self, timeout):
        self.polls.append(timeout)

    def flush(self, _timeout):
        return 0


def test_publishes_versioned_capture_keyed_event():
    producer = FakeProducer()
    publisher = tap.BufferedEventPublisher(
        producer, "capture-events", "capture-42"
    )

    publisher.publish({"type": "capture_complete"})

    topic, record = producer.records[0]
    value = tap.json.loads(record["value"])
    assert topic == "capture-events"
    assert record["key"] == b"capture-42"
    assert value == {
        "schema_version": 1,
        "capture_id": "capture-42",
        "type": "capture_complete",
    }


def test_publishes_distinct_capture_start_timeout_event():
    producer = FakeProducer()
    publisher = tap.BufferedEventPublisher(
        producer, "capture-events", "capture-42"
    )

    publisher.publish(
        {
            "type": "capture_start_timeout",
            "wait_msec": 60000,
            "exit_code": tap.CAPTURE_START_TIMEOUT_EXIT_CODE,
        }
    )

    value = tap.json.loads(producer.records[0][1]["value"])
    assert value["type"] == "capture_start_timeout"
    assert value["wait_msec"] == 60000
    assert value["exit_code"] == 10


def test_start_wait_applies_only_before_first_capture_data():
    assert not tap.capture_start_expired(10.0, None, 60000, now=69.999)
    assert tap.capture_start_expired(10.0, None, 60000, now=70.0)
    assert not tap.capture_start_expired(10.0, 20.0, 60000, now=1000.0)


class RecoveringProducer(FakeProducer):
    def __init__(self, failures):
        super().__init__()
        self.failures = failures

    def produce(self, topic, **kwargs):
        if self.failures:
            self.failures -= 1
            raise BufferError("Kafka queue is full while broker is down")
        super().produce(topic, **kwargs)


def test_buffers_during_kafka_outage_and_replays_in_order():
    producer = RecoveringProducer(failures=2)
    publisher = tap.BufferedEventPublisher(producer, "events", "capture-1")

    publisher.publish({"type": "connection_log", "trace_id": 1})
    publisher.publish({"type": "connection_log", "trace_id": 2})
    assert len(publisher.pending) == 2
    assert producer.records == []

    assert publisher.drain_available()
    events = [tap.json.loads(record[1]["value"]) for record in producer.records]
    assert [event["trace_id"] for event in events] == [1, 2]
    assert not publisher.pending


def test_final_drain_retries_application_buffer():
    producer = RecoveringProducer(failures=1)
    publisher = tap.BufferedEventPublisher(producer, "events", "capture-1")
    publisher.publish({"type": "capture_complete"})
    assert len(publisher.pending) == 1

    publisher.drain_all(timeout_seconds=1)

    assert not publisher.pending
    event = tap.json.loads(producer.records[0][1]["value"])
    assert event["type"] == "capture_complete"
