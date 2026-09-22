#!/usr/bin/env python3
"""Decode Envoy streaming-admin tap segments as they arrive."""

import argparse
import base64
import codecs
from collections import deque
import http.client
import json
import queue
import signal
import socket
import sys
import threading
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

KAFKA_CHUNK_BYTES = 512 * 1024
TAP_QUEUE_CAPACITY = 64
POLL_INTERVAL_SECONDS = 1


class ShutdownRequested(RuntimeError):
    """Raised when shutdown is requested before the tap subscription is ready."""


def optional_wait_msec(value):
    """Parse a wait interval; an empty value or zero means no deadline."""
    if value == "":
        return 0
    try:
        wait_msec = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "must be empty or a non-negative integer"
        ) from error
    if wait_msec < 0:
        raise argparse.ArgumentTypeError("must be empty or a non-negative integer")
    return wait_msec


def next_wait(wait_msec, waiting_since, now=None):
    """Return the next bounded poll duration and whether a deadline expired."""
    if wait_msec == 0:
        return POLL_INTERVAL_SECONDS, False
    now = time.monotonic() if now is None else now
    remaining = wait_msec / 1000 - (now - waiting_since)
    return min(POLL_INTERVAL_SECONDS, max(0, remaining)), remaining <= 0


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


class TapStreamPump:
    """Drain the buffered HTTP response continuously on a reader thread."""

    END = object()

    def __init__(self, reader, capacity=TAP_QUEUE_CAPACITY):
        self.reader = reader
        self.items = queue.Queue(maxsize=capacity)
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()

    def _run(self):
        try:
            while True:
                trace = self.reader.read()
                if trace is None:
                    self._put(self.END)
                    return
                if not self._put(trace):
                    return
        except BaseException as error:
            self._put(error)

    def _put(self, item):
        """Apply bounded backpressure while still allowing prompt shutdown."""
        while not self.stopping.is_set():
            try:
                self.items.put(item, timeout=0.1)
                return True
            except queue.Full:
                pass
        return False

    def get(self, timeout):
        item = self.items.get(timeout=timeout)
        if item is self.END:
            return None
        if isinstance(item, BaseException):
            raise item
        return item

    def stop(self, connection, response, timeout=5):
        """Interrupt the blocking HTTP read and wait for the reader to exit."""
        self.stopping.set()
        sock = connection.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        response.close()
        self.thread.join(timeout)
        if self.thread.is_alive():
            raise RuntimeError("Envoy tap reader thread did not stop")


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


def subscribe(args, shutdown_requested):
    admin = urllib.parse.urlsplit(args.admin_url)
    while True:
        if shutdown_requested.is_set():
            raise ShutdownRequested
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
            if shutdown_requested.wait(1):
                raise ShutdownRequested


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


def publish_connection(publisher, trace_id, path, chunk_bytes=KAFKA_CHUNK_BYTES):
    """Publish a log in records safely below Kafka's default message limit."""
    chunk_count = 0
    with path.open("rb") as source:
        while chunk := source.read(chunk_bytes):
            publisher.publish(
                {
                    "type": "connection_log_chunk",
                    "trace_id": trace_id,
                    "filename": path.name,
                    "chunk_index": chunk_count,
                    "payload_base64": base64.b64encode(chunk).decode("ascii"),
                }
            )
            chunk_count += 1
    publisher.publish(
        {
            "type": "connection_log_complete",
            "trace_id": trace_id,
            "filename": path.name,
            "chunk_count": chunk_count,
        }
    )

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-url", required=True)
    parser.add_argument("--config-id", required=True)
    parser.add_argument("--tap-directory", type=Path, required=True)
    parser.add_argument("--decoded-directory", type=Path, required=True)
    parser.add_argument(
        "--wait-for-next-tap-before-finish-msec",
        type=optional_wait_msec,
        required=True,
    )
    parser.add_argument(
        "--wait-for-first-tap-before-finish-msec",
        type=optional_wait_msec,
        required=True,
    )
    parser.add_argument("--max-buffered-rx-bytes", type=int, default=16777216)
    parser.add_argument("--retain-raw-taps", action="store_true")
    parser.add_argument("--kafka-brokers", required=True)
    parser.add_argument("--kafka-topic", required=True)
    parser.add_argument("--kafka-delivery-timeout-seconds", type=int, default=120)
    parser.add_argument("--capture-id", required=True)
    parser.add_argument("--ready-file", type=Path)
    args = parser.parse_args()
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
    publisher = BufferedEventPublisher(
        producer, args.kafka_topic, args.capture_id
    )
    shutdown_requested = threading.Event()

    def request_shutdown(_signum, _frame):
        shutdown_requested.set()

    signal.signal(signal.SIGHUP, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGQUIT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)
    try:
        connection, response = subscribe(args, shutdown_requested)
    except ShutdownRequested:
        publisher.publish({"type": "capture_complete"})
        publisher.drain_all(args.kafka_delivery_timeout_seconds)
        return 0
    trace_reader = StreamingJsonTraceReader(response)
    trace_pump = TapStreamPump(trace_reader)
    trace_pump.start()
    if args.ready_file:
        args.ready_file.touch()
    active_trace_ids = set()
    traces_with_data = set()
    capture_failed = False

    def capture_trace(trace):
        trace_id, closed = trace_id_and_closed(trace)
        active_trace_ids.add(trace_id)
        stream_path = spool_directory / f"connection_{trace_id}.stream"
        received_data = append_received_data(trace, stream_path)
        if args.retain_raw_taps:
            raw_path = args.tap_directory / f"connection_{trace_id}.pb"
            payload = trace.SerializeToString()
            with raw_path.open("ab") as raw_output:
                raw_output.write(encode_varint(len(payload)) + payload)

        if received_data:
            traces_with_data.add(trace_id)
        if closed:
            if trace_id in traces_with_data:
                destination = args.decoded_directory / f"connection_{trace_id}.log"
                published_path = finalize_stream(stream_path, destination)
                publish_connection(publisher, trace_id, published_path)
                traces_with_data.remove(trace_id)
            else:
                stream_path.unlink(missing_ok=True)
            active_trace_ids.remove(trace_id)

    def next_trace(timeout):
        publisher.drain_available()
        trace = trace_pump.get(timeout=timeout)
        if trace is None:
            raise RuntimeError("Envoy closed the streaming admin tap")
        capture_trace(trace)

    def wait_for_first_trace():
        waiting_since = time.monotonic()
        start_timed_out = False
        while not (shutdown_requested.is_set() or start_timed_out):
            timeout, start_timed_out = next_wait(
                args.wait_for_first_tap_before_finish_msec, waiting_since
            )
            if start_timed_out:
                continue
            try:
                next_trace(timeout)
                return False
            except queue.Empty:
                pass
        return start_timed_out

    def wait_for_next_trace():
        waiting_since = time.monotonic()
        while not shutdown_requested.is_set():
            timeout, wait_finished = next_wait(
                args.wait_for_next_tap_before_finish_msec, waiting_since
            )
            if wait_finished:
                return
            try:
                next_trace(timeout)
                waiting_since = time.monotonic()
            except queue.Empty:
                pass

    def capture_until_finished():
        start_timed_out = wait_for_first_trace()
        if start_timed_out or shutdown_requested.is_set():
            return start_timed_out
        wait_for_next_trace()
        return False

    try:
        start_timed_out = capture_until_finished()
    except BaseException:
        capture_failed = True
        # Preserve every event accepted before a capture-side failure.
        publisher.drain_all(args.kafka_delivery_timeout_seconds)
        raise
    finally:
        trace_pump.stop(connection, response)
        connection.close()
        if shutdown_requested.is_set() and not capture_failed:
            # The reader may already have decoded records before SIGTERM was
            # observed by the main loop. Include that bounded queue in the
            # capture before finalizing its partial streams.
            while True:
                try:
                    trace = trace_pump.get(timeout=0)
                except queue.Empty:
                    break
                if trace is None:
                    break
                capture_trace(trace)

    if start_timed_out:
        for stream_path in spool_directory.glob("*.stream"):
            stream_path.unlink()
        spool_directory.rmdir()
        publisher.publish({
            "type": "capture_start_timeout",
            "wait_msec": args.wait_for_first_tap_before_finish_msec,
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
    spool_directory.rmdir()
    publisher.publish({"type": "capture_complete"})
    publisher.drain_all(args.kafka_delivery_timeout_seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
