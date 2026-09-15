#!/usr/bin/env python3
"""Decode Envoy streaming-admin tap segments as they arrive."""

import argparse
import base64
import codecs
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

    def read(self):
        while True:
            self.buffer = self.buffer.lstrip()
            if self.buffer:
                try:
                    value, end = self.decoder.raw_decode(self.buffer)
                except json.JSONDecodeError:
                    pass
                else:
                    self.buffer = self.buffer[end:]
                    trace = wrapper_pb2.TraceWrapper()
                    # Envoy may add event metadata before the bundled xDS
                    # Python descriptors are updated (for example seq_num).
                    # Unknown metadata is safe to ignore: capture uses only
                    # trace identity, event kind, and body bytes.
                    json_format.ParseDict(value, trace, ignore_unknown_fields=True)
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


def stats_rx_bytes(admin):
    connection = http.client.HTTPConnection(admin.hostname, admin.port, timeout=2)
    path = "/stats?filter=%5Etcp%5C.destination%5C.downstream_cx_rx_bytes_total%24"
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        if response.status != 200:
            return None
        for line in response.read().decode().splitlines():
            if line.startswith("tcp.destination.downstream_cx_rx_bytes_total:"):
                return int(line.rsplit(":", 1)[1])
    finally:
        connection.close()
    return None


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


def append_received_bytes(trace, stream_path):
    """Decode one protobuf segment and return the downstream RX byte count."""
    received = 0
    with stream_path.open("ab") as output:
        for event in events_from_trace(trace):
            chunk = bytes_from_event(event)
            if chunk:
                output.write(chunk)
                received += len(chunk)
    return received


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
DELIVERY_ERRORS = []


def delivery_report(error, _message):
    if error is not None:
        DELIVERY_ERRORS.append(str(error))


def publish_event(producer, topic, capture_id, event):
    event["schema_version"] = 1
    event["capture_id"] = capture_id
    producer.produce(
        topic,
        key=capture_id.encode(),
        value=json.dumps(event, separators=(",", ":")).encode(),
        on_delivery=delivery_report,
    )
    producer.poll(0)


def flush_events(producer):
    remaining = producer.flush(30)
    if remaining or DELIVERY_ERRORS:
        details = "; ".join(DELIVERY_ERRORS) or "delivery timeout"
        raise RuntimeError(f"Kafka event delivery failed: {details}")


def publish_connection(producer, topic, capture_id, trace_id, path):
    publish_event(producer, topic, capture_id, {
        "type": "connection_log",
        "trace_id": trace_id,
        "filename": path.name,
        "payload_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
    })



def capture_start_expired(started, last_activity, wait_msec, now=None):
    if last_activity is not None:
        return False
    now = time.monotonic() if now is None else now
    return now - started >= wait_msec / 1000


def wait_for_broker(client, timeout_seconds):
    """Wait until broker metadata can be fetched over its advertised listener."""
    deadline = time.monotonic() + timeout_seconds
    last_error = None
    while time.monotonic() < deadline:
        try:
            remaining = max(0.1, deadline - time.monotonic())
            client.list_topics(timeout=min(5, remaining))
            return
        except Exception as error:
            last_error = error
            print(f"Waiting for event broker: {error}", file=sys.stderr, flush=True)
            time.sleep(min(1, max(0, deadline - time.monotonic())))
    raise RuntimeError(
        f"event broker was not ready within {timeout_seconds} seconds"
    ) from last_error

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
    parser.add_argument("--kafka-startup-timeout-seconds", type=int, default=120)
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
    })
    wait_for_broker(producer, args.kafka_startup_timeout_seconds)
    connection, response = subscribe(args)
    trace_reader = StreamingJsonTraceReader(response)
    if args.ready_file:
        args.ready_file.touch()
    admin = urllib.parse.urlsplit(args.admin_url)
    started = time.monotonic()
    last_activity = None
    last_rx = stats_rx_bytes(admin)
    active_trace_ids = set()
    traces_with_data = set()
    start_timed_out = False
    try:
        while time.monotonic() - started < args.max_wait_msec / 1000:
            try:
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
                received_bytes = append_received_bytes(trace, stream_path)
                if args.retain_raw_taps:
                    raw_path = args.tap_directory / f"connection_{trace_id}.pb"
                    payload = trace.SerializeToString()
                    with raw_path.open("ab") as raw_output:
                        raw_output.write(encode_varint(len(payload)) + payload)

                if received_bytes:
                    traces_with_data.add(trace_id)
                    last_activity = time.monotonic()
                if closed:
                    if trace_id in traces_with_data:
                        destination = args.decoded_directory / f"connection_{trace_id}.log"
                        published_path = finalize_stream(stream_path, destination)
                        publish_connection(
                            producer,
                            args.kafka_topic,
                            args.capture_id,
                            trace_id,
                            published_path,
                        )
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
                current_rx = stats_rx_bytes(admin)
                if current_rx is not None and current_rx != last_rx:
                    last_rx = current_rx
                    last_activity = now
                if now - last_activity >= args.quiet_msec / 1000:
                    break
        else:
            raise TimeoutError("timed out waiting for tapped traffic to become quiet")
    finally:
        connection.close()

    if start_timed_out:
        for stream_path in spool_directory.glob("*.stream"):
            stream_path.unlink()
        spool_directory.rmdir()
        publish_event(producer, args.kafka_topic, args.capture_id, {
            "type": "capture_start_timeout",
            "wait_msec": args.wait_before_start_msec,
            "exit_code": CAPTURE_START_TIMEOUT_EXIT_CODE,
        })
        flush_events(producer)
        return CAPTURE_START_TIMEOUT_EXIT_CODE

    # Docker logging connections commonly stay open. At the bounded-batch
    # quiet boundary, publish every complete protobuf segment received so far.
    for trace_id in sorted(active_trace_ids):
        stream_path = spool_directory / f"connection_{trace_id}.stream"
        destination = args.decoded_directory / f"connection_{trace_id}.log"
        published_path = finalize_stream(stream_path, destination)
        publish_connection(
            producer, args.kafka_topic, args.capture_id, trace_id, published_path
        )
        published_path.unlink()
    spool_directory.rmdir()
    publish_event(producer, args.kafka_topic, args.capture_id, {"type": "capture_complete"})
    flush_events(producer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
