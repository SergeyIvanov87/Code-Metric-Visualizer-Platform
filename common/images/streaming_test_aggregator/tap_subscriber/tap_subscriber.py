#!/usr/bin/env python3
"""Decode Envoy streaming-admin tap segments as they arrive."""

import argparse
import base64
import codecs
from collections import deque
import http.client
import json
import select
import sys
import time
import urllib.parse
from pathlib import Path

from confluent_kafka import Producer
from envoy.data.tap.v3 import wrapper_pb2
from google.protobuf import json_format

from decode_envoy_tap import (
    bytes_from_event,
    events_from_trace,
    frame_syslog_stream,
    producer_output_path,
)


def encode_varint(value):
    encoded = bytearray()
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


class StreamingJsonTraceReader:
    """Parse adjacent JSON objects from an Envoy streaming-admin response."""

    def __init__(self, response):
        self.response = response
        self.buffer = ""
        self.decoder = json.JSONDecoder()
        self.utf8_decoder = codecs.getincrementaldecoder("utf-8")()

    def pop_buffered(self):
        """Return a complete buffered trace without reading the socket."""
        self.buffer = self.buffer.lstrip()
        if not self.buffer:
            return None
        try:
            value, end = self.decoder.raw_decode(self.buffer)
        except json.JSONDecodeError:
            return None

        self.buffer = self.buffer[end:]
        trace = wrapper_pb2.TraceWrapper()
        # Envoy may add event metadata before the bundled xDS Python
        # descriptors are updated (for example seq_num). Unknown metadata is
        # safe to ignore: capture uses only identity, event kind, and bytes.
        json_format.ParseDict(value, trace, ignore_unknown_fields=True)
        return trace

    def read(self):
        while True:
            trace = self.pop_buffered()
            if trace is not None:
                return trace

            # read1 returns currently available response data instead of waiting
            # for a full buffer, which is essential for a never-ending stream.
            chunk = self.response.read1(65536)
            if chunk:
                self.buffer += self.utf8_decoder.decode(chunk)
                continue

            self.buffer += self.utf8_decoder.decode(b"", final=True)
            if self.buffer.strip():
                raise ValueError("Envoy returned a truncated tap JSON object")
            return None


def trace_id_and_closed(trace):
    if trace.WhichOneof("trace") != "socket_streamed_trace_segment":
        raise ValueError("streaming admin tap returned a non-streamed socket trace")
    segment = trace.socket_streamed_trace_segment
    events = []
    piece = segment.WhichOneof("message_piece")
    if piece == "event":
        events.append(segment.event)
    elif piece == "events":
        events.extend(segment.events.events)
    closed = any(event.WhichOneof("event_selector") == "closed" for event in events)
    return segment.trace_id, closed


def subscribe(args):
    admin = urllib.parse.urlsplit(args.admin_url)
    deadline = time.monotonic() + args.max_wait_msec / 1000
    while True:
        try:
            connection = http.client.HTTPConnection(admin.hostname, admin.port, timeout=2)
            body = json.dumps({
                "configId": args.config_id,
                "tapConfig": {
                    "match": {"anyMatch": True},
                    "outputConfig": {
                        "streaming": True,
                        "maxBufferedRxBytes": args.max_buffered_rx_bytes,
                        "sinks": [{
                            "format": "JSON_BODY_AS_BYTES",
                            "streamingAdmin": {}
                        }]
                    }
                }
            })
            path = "/tap?" + urllib.parse.urlencode({"config_id": args.config_id})
            connection.request("POST", path, body, {"Content-Type": "application/json"})
            response = connection.getresponse()
            if response.status == 200:
                # Keep the buffered HTTP reader in blocking mode. A timeout in
                # socket.makefile() can poison subsequent reads; select drives
                # the one-second inactivity checks without touching the reader.
                connection.sock.settimeout(None)
                return connection, response
            message = response.read().decode(errors="replace")
            connection.close()
            raise RuntimeError(f"Envoy /tap returned HTTP {response.status}: {message}")
        except (OSError, RuntimeError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)


def append_received_data(trace, stream_path):
    """Append downstream data from one trace and report whether any arrived."""
    received_data = False
    with stream_path.open("ab") as output:
        for event in events_from_trace(trace):
            chunk = bytes_from_event(event)
            if chunk:
                output.write(chunk)
                received_data = True
    return received_data


def finalize_stream(stream_path, destination):
    """Frame a reconstructed connection stream and atomically publish it."""
    stream = stream_path.read_bytes() if stream_path.exists() else b""
    records = frame_syslog_stream(stream)
    destination = producer_output_path(destination, records)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("wb") as output:
        for record in records:
            output.write(record + b"\n")
    temporary.replace(destination)
    stream_path.unlink(missing_ok=True)
    return destination



CAPTURE_START_TIMEOUT_EXIT_CODE = 10


class BufferedEventPublisher:
    """Preserve event order while Kafka or its network is unavailable."""

    def __init__(self, producer, topic, capture_id):
        self.producer = producer
        self.topic = topic
        self.key = capture_id.encode()
        self.capture_id = capture_id
        self.pending = deque()
        self.delivery_failures = deque()

    def _delivery_report(self, record):
        def callback(error, _message):
            if error is not None:
                self.delivery_failures.append((record, str(error)))

        return callback

    def publish(self, event):
        event = dict(event)
        event["schema_version"] = 1
        event["capture_id"] = self.capture_id
        self.pending.append(json.dumps(event, separators=(",", ":")).encode())
        self.drain_available()

    def drain_available(self):
        """Move buffered records to librdkafka without blocking tap reads."""
        self.producer.poll(0)
        while self.delivery_failures:
            record, error = self.delivery_failures.pop()
            print(f"Retrying Kafka event after delivery failure: {error}", file=sys.stderr)
            self.pending.appendleft(record)

        while self.pending:
            record = self.pending[0]
            try:
                self.producer.produce(
                    self.topic,
                    key=self.key,
                    value=record,
                    on_delivery=self._delivery_report(record),
                )
            except BufferError:
                # librdkafka's local queue is full. Keep this record in the
                # application queue and resume consuming Envoy immediately.
                self.producer.poll(0)
                return False
            self.pending.popleft()
            self.producer.poll(0)
        return True

    def drain_all(self, timeout_seconds):
        """Drain application and librdkafka buffers before termination."""
        deadline = time.monotonic() + timeout_seconds
        while True:
            self.drain_available()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if self.pending:
                self.producer.poll(min(0.1, remaining))
                continue
            undelivered = self.producer.flush(min(0.5, remaining))
            self.producer.poll(0)
            if not undelivered and not self.delivery_failures:
                return

        raise RuntimeError(
            "Kafka event delivery did not recover within "
            f"{timeout_seconds} seconds; {len(self.pending)} application-buffered "
            "events remain"
        )


def publish_connection(publisher, trace_id, path):
    publisher.publish(
        {
            "type": "connection_log",
            "trace_id": trace_id,
            "filename": path.name,
            "payload_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
        }
    )

def capture_start_expired(started, last_activity, wait_msec, now=None):
    if last_activity is not None:
        return False
    now = time.monotonic() if now is None else now
    return now - started >= wait_msec / 1000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-url", required=True)
    parser.add_argument("--config-id", required=True)
    parser.add_argument("--tap-directory", type=Path, required=True)
    parser.add_argument("--decoded-directory", type=Path, required=True)
    parser.add_argument("--quiet-msec", type=int, required=True)
    parser.add_argument("--wait-before-start-msec", type=int, required=True)
    parser.add_argument("--max-wait-msec", type=int, required=True)
    parser.add_argument("--max-buffered-rx-bytes", type=int, default=16777216)
    parser.add_argument("--retain-raw-taps", action="store_true")
    parser.add_argument("--kafka-brokers", required=True)
    parser.add_argument("--kafka-topic", required=True)
    parser.add_argument("--kafka-delivery-timeout-seconds", type=int, default=120)
    parser.add_argument("--capture-id", required=True)
    parser.add_argument("--ready-file", type=Path)
    args = parser.parse_args()
    if args.wait_before_start_msec < 1:
        parser.error("--wait-before-start-msec must be positive")
    if args.max_wait_msec < args.wait_before_start_msec:
        parser.error("--max-wait-msec must not be shorter than --wait-before-start-msec")
    args.tap_directory.mkdir(parents=True, exist_ok=True)
    args.decoded_directory.mkdir(parents=True, exist_ok=True)
    spool_directory = args.decoded_directory / ".spool"
    spool_directory.mkdir()

    producer = Producer({
        "bootstrap.servers": args.kafka_brokers,
        "enable.idempotence": True,
        "acks": "all",
        # Retriable broker/network failures must not expire accepted events.
        # drain_all supplies the bounded process-level shutdown deadline.
        "message.timeout.ms": 0,
    })
    connection, response = subscribe(args)
    publisher = BufferedEventPublisher(
        producer, args.kafka_topic, args.capture_id
    )
    trace_reader = StreamingJsonTraceReader(response)
    if args.ready_file:
        args.ready_file.touch()
    started = time.monotonic()
    last_activity = None
    active_trace_ids = set()
    traces_with_data = set()
    start_timed_out = False
    try:
        while time.monotonic() - started < args.max_wait_msec / 1000:
            try:
                # Retry application-buffered events first on every capture
                # iteration, but never block reading Envoy on Kafka recovery.
                publisher.drain_available()
                # One socket read may contain several adjacent JSON objects.
                # Drain those objects before waiting for more network data;
                # otherwise the quiet timer can end the capture while complete
                # trace events are still buffered in this process.
                trace = trace_reader.pop_buffered()
                if trace is None:
                    if not select.select([connection.sock], [], [], 1)[0]:
                        raise TimeoutError
                    trace = trace_reader.read()
                if trace is None:
                    raise RuntimeError("Envoy closed the streaming admin tap")
                trace_id, closed = trace_id_and_closed(trace)
                active_trace_ids.add(trace_id)

                # JSON-to-protobuf conversion happens while the admin response
                # is live. Only reconstructed downstream bytes are spooled.
                stream_path = spool_directory / f"connection_{trace_id}.stream"
                received_data = append_received_data(trace, stream_path)
                if args.retain_raw_taps:
                    raw_path = args.tap_directory / f"connection_{trace_id}.pb"
                    payload = trace.SerializeToString()
                    with raw_path.open("ab") as raw_output:
                        raw_output.write(encode_varint(len(payload)) + payload)

                if received_data:
                    traces_with_data.add(trace_id)
                    last_activity = time.monotonic()
                if closed:
                    if trace_id in traces_with_data:
                        destination = args.decoded_directory / f"connection_{trace_id}.log"
                        published_path = finalize_stream(stream_path, destination)
                        publish_connection(publisher, trace_id, published_path)
                        published_path.unlink()
                        traces_with_data.remove(trace_id)
                    else:
                        stream_path.unlink(missing_ok=True)
                    active_trace_ids.remove(trace_id)
                if capture_start_expired(
                    started, last_activity, args.wait_before_start_msec
                ):
                    start_timed_out = True
                    break
            except TimeoutError:
                now = time.monotonic()
                if last_activity is None:
                    if capture_start_expired(
                        started, last_activity, args.wait_before_start_msec, now
                    ):
                        start_timed_out = True
                        break
                    continue
                # A partial JSON object proves that a tap event is still in
                # flight even though no complete downstream payload can be
                # decoded yet. Wait for its remainder or the absolute capture
                # deadline instead of declaring the stream quiet.
                if trace_reader.buffer.strip():
                    continue
                if now - last_activity >= args.quiet_msec / 1000:
                    break
        else:
            raise TimeoutError("timed out waiting for tapped traffic to become quiet")
    except BaseException:
        # Preserve every event accepted before a capture-side failure. This is
        # also the max-capture-timeout path.
        publisher.drain_all(args.kafka_delivery_timeout_seconds)
        raise
    finally:
        connection.close()

    if start_timed_out:
        for stream_path in spool_directory.glob("*.stream"):
            stream_path.unlink()
        spool_directory.rmdir()
        publisher.publish({
            "type": "capture_start_timeout",
            "wait_msec": args.wait_before_start_msec,
            "exit_code": CAPTURE_START_TIMEOUT_EXIT_CODE,
        })
        publisher.drain_all(args.kafka_delivery_timeout_seconds)
        return CAPTURE_START_TIMEOUT_EXIT_CODE

    # Docker logging connections commonly stay open. At the bounded-batch
    # quiet boundary, publish every complete protobuf segment received so far.
    for trace_id in sorted(active_trace_ids):
        stream_path = spool_directory / f"connection_{trace_id}.stream"
        destination = args.decoded_directory / f"connection_{trace_id}.log"
        published_path = finalize_stream(stream_path, destination)
        publish_connection(publisher, trace_id, published_path)
        published_path.unlink()
    spool_directory.rmdir()
    publisher.publish({"type": "capture_complete"})
    publisher.drain_all(args.kafka_delivery_timeout_seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
