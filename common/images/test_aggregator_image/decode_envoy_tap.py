#!/usr/bin/env python3

"""Decode one completed Envoy socket-tap trace into syslog records."""

import argparse
import os
import re
from pathlib import Path

from envoy.data.tap.v3 import wrapper_pb2
from google.protobuf.message import DecodeError


# Docker's default Unix syslog formatter emits RFC3164-like records. Its TCP
# framer adds no delimiter, so record boundaries must be recovered from the
# next complete header after the connection byte stream has been reconstructed.
SYSLOG_HEADER = re.compile(
    rb"<\d{1,3}>[A-Z][a-z]{2} [ 0-9][0-9] "
    rb"[0-9]{2}:[0-9]{2}:[0-9]{2} "
    rb"(?:(?P<hostname>[^\s:\[]+) )?"
    rb"(?P<producer>[^\s:\[]+)(?:\[\d+\])?: ?"
)


DEFAULT_MAX_BUFFERED_RX_BYTES = "16777216"


def truncation_error(subject):
    configured_limit = os.environ.get(
        "MAX_BUFFERED_RX_BYTES", DEFAULT_MAX_BUFFERED_RX_BYTES
    )
    return ValueError(
        f"Envoy marked {subject} as truncated. Configured max_buffered_rx_bytes "
        f"is {configured_limit} bytes. Increase MAX_BUFFERED_RX_BYTES in the "
        "Docker Compose configuration and retry."
    )


def decode_varint32(data, offset):
    """Decode one protobuf uint32 length prefix without parsing its message."""
    value = 0
    start = offset
    for shift in range(0, 35, 7):
        if offset >= len(data):
            raise ValueError(
                f"truncated protobuf length prefix at byte offset {start}"
            )
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            if value > 0xFFFFFFFF:
                raise ValueError(
                    f"protobuf message length exceeds uint32 at byte offset {start}"
                )
            return value, offset
    raise ValueError(f"invalid protobuf length prefix at byte offset {start}")


def iter_trace_wrappers(data):
    """Yield TraceWrapper messages from Envoy's length-delimited tap format."""
    offset = 0
    message_number = 0
    while offset < len(data):
        message_number += 1
        length, payload_offset = decode_varint32(data, offset)
        end = payload_offset + length
        if end > len(data):
            raise ValueError(
                "truncated protobuf message "
                f"{message_number}: declared {length} bytes at byte offset {offset}, "
                f"only {len(data) - payload_offset} remain"
            )

        trace = wrapper_pb2.TraceWrapper()
        try:
            trace.ParseFromString(data[payload_offset:end])
        except DecodeError as error:
            raise ValueError(
                f"invalid Envoy TraceWrapper protobuf message {message_number}"
            ) from error
        yield trace
        offset = end


def decode_body(body):
    if body.truncated:
        raise truncation_error("a captured body")
    body_type = body.WhichOneof("body_type")
    if body_type == "as_bytes":
        return bytes(body.as_bytes)
    if body_type == "as_string":
        return body.as_string.encode("utf-8")
    return b""


def bytes_from_event(event):
    if event.WhichOneof("event_selector") != "read":
        return b""
    return decode_body(event.read.data)


def events_from_trace(trace):
    trace_type = trace.WhichOneof("trace")
    if trace_type == "socket_buffered_trace":
        buffered = trace.socket_buffered_trace
        if buffered.read_truncated:
            raise truncation_error("the downstream socket trace")
        yield from buffered.events
        return

    if trace_type == "socket_streamed_trace_segment":
        streamed = trace.socket_streamed_trace_segment
        message_piece = streamed.WhichOneof("message_piece")
        if message_piece == "event":
            yield streamed.event
        elif message_piece == "events":
            yield from streamed.events.events
        return

    if trace_type is None:
        raise ValueError("Envoy TraceWrapper contains no trace")
    raise ValueError(f"unsupported Envoy tap trace type: {trace_type}")


def extract_downstream_bytes(trace_data):
    chunks = []
    for trace in iter_trace_wrappers(trace_data):
        for event in events_from_trace(trace):
            chunk = bytes_from_event(event)
            if chunk:
                chunks.append(chunk)
    return b"".join(chunks)


def frame_syslog_stream(stream):
    starts = [match.start() for match in SYSLOG_HEADER.finditer(stream)]
    if not starts:
        # The listener health check also passes through Envoy and uses RFC5424
        # octet-counting. It is intentionally irrelevant to pytest aggregation.
        # A tester stream without a recognizable header, however, must fail
        # loudly rather than disappear from the result.
        if b"tester" in stream.lower():
            raise ValueError(
                "captured tester data contains no recognizable Docker syslog header"
            )
        return []
    prefix = stream[: starts[0]].strip(b"\x00\r\n \t")
    if prefix and b"tester" in prefix.lower():
        raise ValueError("unframed bytes precede the first recognizable syslog record")

    starts.append(len(stream))
    return [
        stream[start:end].rstrip(b"\r\n")
        for start, end in zip(starts, starts[1:])
    ]


def producer_output_path(output_file, records):
    producers = []
    for record in records:
        match = SYSLOG_HEADER.match(record)
        if match is None:
            continue
        producer = re.sub(
            rb"[^A-Za-z0-9_.-]+",
            b"_",
            match.group("producer"),
        ).strip(b"._")
        if producer and producer not in producers:
            producers.append(producer)

    if len(producers) > 1:
        names = ", ".join(name.decode("ascii") for name in producers)
        raise ValueError(
            "one Envoy connection contains records from multiple syslog producers: "
            f"{names}"
        )
    if not producers:
        return output_file

    producer = producers[0].decode("ascii")
    return output_file.with_name(f"{producer}__{output_file.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tap_file", type=Path)
    parser.add_argument("output_file", type=Path)
    parser.add_argument(
        "--name-by-producer",
        action="store_true",
        help="prefix the output filename with the syslog producer tag",
    )
    args = parser.parse_args()

    trace_data = args.tap_file.read_bytes()
    stream = extract_downstream_bytes(trace_data)
    records = frame_syslog_stream(stream)

    output_file = args.output_file
    if args.name_by_producer:
        output_file = producer_output_path(output_file, records)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_file.with_suffix(output_file.suffix + ".tmp")
    with temporary.open("wb") as output:
        for record in records:
            output.write(record)
            output.write(b"\n")
    temporary.replace(output_file)


if __name__ == "__main__":
    main()
