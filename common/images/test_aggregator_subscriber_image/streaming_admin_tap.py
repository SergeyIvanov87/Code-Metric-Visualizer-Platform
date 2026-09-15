#!/usr/bin/env python3
"""Subscribe to Envoy's streaming admin tap and persist per-connection traces."""

import argparse
import http.client
import json
import subprocess
import time
import urllib.parse
from pathlib import Path

from envoy.data.tap.v3 import wrapper_pb2


def encode_varint(value):
    encoded = bytearray()
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def read_varint(response):
    value = 0
    for shift in range(0, 35, 7):
        byte = response.read(1)
        if not byte:
            return None
        value |= (byte[0] & 0x7F) << shift
        if byte[0] < 0x80:
            return value
    raise ValueError("invalid protobuf length prefix from Envoy")


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
                            "format": "PROTO_BINARY_LENGTH_DELIMITED",
                            "streamingAdmin": {}
                        }]
                    }
                }
            })
            path = "/tap?" + urllib.parse.urlencode({"config_id": args.config_id})
            connection.request("POST", path, body, {"Content-Type": "application/json"})
            response = connection.getresponse()
            if response.status == 200:
                connection.sock.settimeout(1)
                return connection, response
            message = response.read().decode(errors="replace")
            connection.close()
            raise RuntimeError(f"Envoy /tap returned HTTP {response.status}: {message}")
        except (OSError, RuntimeError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-url", required=True)
    parser.add_argument("--config-id", required=True)
    parser.add_argument("--tap-directory", type=Path, required=True)
    parser.add_argument("--decoded-directory", type=Path, required=True)
    parser.add_argument("--quiet-msec", type=int, required=True)
    parser.add_argument("--max-wait-msec", type=int, required=True)
    parser.add_argument("--max-buffered-rx-bytes", type=int, default=16777216)
    parser.add_argument("--ready-file", type=Path)
    args = parser.parse_args()
    args.tap_directory.mkdir(parents=True, exist_ok=True)
    args.decoded_directory.mkdir(parents=True, exist_ok=True)

    connection, response = subscribe(args)
    if args.ready_file:
        args.ready_file.touch()
    admin = urllib.parse.urlsplit(args.admin_url)
    started = last_activity = time.monotonic()
    last_rx = stats_rx_bytes(admin)
    files = {}
    completed = []
    try:
        while time.monotonic() - started < args.max_wait_msec / 1000:
            try:
                length = read_varint(response)
                if length is None:
                    raise RuntimeError("Envoy closed the streaming admin tap")
                payload = response.read(length)
                if len(payload) != length:
                    raise RuntimeError("Envoy returned a truncated tap protobuf")
                trace = wrapper_pb2.TraceWrapper()
                trace.ParseFromString(payload)
                trace_id, closed = trace_id_and_closed(trace)
                path = args.tap_directory / f"connection_{trace_id}.pb"
                if trace_id not in files:
                    files[trace_id] = path.open("ab")
                output = files[trace_id]
                output.write(encode_varint(length) + payload)
                output.flush()
                last_activity = time.monotonic()
                if closed:
                    output.close()
                    del files[trace_id]
                    completed.append(path)
            except TimeoutError:
                current_rx = stats_rx_bytes(admin)
                if current_rx is not None and current_rx != last_rx:
                    last_rx = current_rx
                    last_activity = time.monotonic()
                if time.monotonic() - last_activity >= args.quiet_msec / 1000:
                    break
        else:
            raise TimeoutError("timed out waiting for tapped traffic to become quiet")
    finally:
        connection.close()
        for output in files.values():
            output.close()

    # A streamed response can be deliberately closed after the quiet period;
    # complete protobuf segments already persisted are valid decoder input.
    completed.extend(
        path for trace_id, path in
        ((int(path.stem.rsplit("_", 1)[1]), path) for path in args.tap_directory.glob("connection_*.pb"))
        if trace_id in files
    )
    for path in sorted(set(completed)):
        destination = args.decoded_directory / f"{path.stem}.log"
        subprocess.run(
            ["python3", "/package/decode_envoy_tap.py", str(path), str(destination), "--name-by-producer"],
            check=True,
        )


if __name__ == "__main__":
    main()
