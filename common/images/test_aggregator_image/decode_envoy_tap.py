#!/usr/bin/env python3

"""Decode one completed Envoy socket-tap trace into syslog records."""

import argparse
import base64
import binascii
import json
import re
from pathlib import Path


# Docker's default Unix syslog formatter emits RFC3164-like records. Its TCP
# framer adds no delimiter, so record boundaries must be recovered from the
# next complete header after the connection byte stream has been reconstructed.
SYSLOG_HEADER = re.compile(
    rb"<\d{1,3}>[A-Z][a-z]{2} [ 0-9][0-9] "
    rb"[0-9]{2}:[0-9]{2}:[0-9]{2} "
    rb"(?:(?P<hostname>[^\s:\[]+) )?"
    rb"(?P<producer>[^\s:\[]+)(?:\[\d+\])?: ?"
)


def iter_json_documents(data):
    decoder = json.JSONDecoder()
    offset = 0
    while offset < len(data):
        while offset < len(data) and data[offset].isspace():
            offset += 1
        if offset == len(data):
            return
        document, offset = decoder.raw_decode(data, offset)
        yield document


def get_field(mapping, snake_name, camel_name=None):
    if not isinstance(mapping, dict):
        return None
    if snake_name in mapping:
        return mapping[snake_name]
    return mapping.get(camel_name) if camel_name else None


def decode_body(body):
    if not isinstance(body, dict):
        return b""
    if body.get("truncated"):
        raise ValueError("Envoy marked a captured body as truncated")
    encoded = get_field(body, "as_bytes", "asBytes")
    if encoded is not None:
        try:
            return base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("invalid base64 body in Envoy tap trace") from error
    string = get_field(body, "as_string", "asString")
    if string is not None:
        return string.encode("utf-8")
    return b""


def bytes_from_event(event):
    if not isinstance(event, dict) or "read" not in event:
        return b""
    return decode_body(event["read"].get("data", {}))


def events_from_document(document):
    buffered = get_field(document, "socket_buffered_trace", "socketBufferedTrace")
    if buffered is not None:
        if get_field(buffered, "read_truncated", "readTruncated"):
            raise ValueError("Envoy marked the downstream socket trace as truncated")
        yield from buffered.get("events", [])
        return

    streamed = get_field(
        document, "socket_streamed_trace_segment", "socketStreamedTraceSegment"
    )
    if streamed is None:
        return
    event = streamed.get("event")
    if event is not None:
        yield event
    event_group = streamed.get("events", {})
    if isinstance(event_group, dict):
        yield from event_group.get("events", [])


def extract_downstream_bytes(trace_text):
    chunks = []
    for document in iter_json_documents(trace_text):
        for event in events_from_document(document):
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

    trace_text = args.tap_file.read_text(encoding="utf-8")
    stream = extract_downstream_bytes(trace_text)
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
