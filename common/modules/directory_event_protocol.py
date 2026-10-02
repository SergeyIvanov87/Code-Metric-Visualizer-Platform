"""Helpers for consuming the streaming-directory-events FIFO protocol."""

import json


def parse_directory_event_stream(stream):
    """Read JSON-Line batch envelopes through EOF and return their events."""
    events = []
    previous_sequence = None
    for raw_line in stream:
        if isinstance(raw_line, bytes):
            raw_line = raw_line.decode("utf-8")
        if not raw_line.strip():
            continue
        record = json.loads(raw_line)
        if not isinstance(record, dict):
            raise ValueError("directory event record must be a JSON object")
        if record.get("type") == "transport_closed":
            continue
        batch = record.get("events")
        if not isinstance(batch, list) or not batch:
            raise ValueError("directory event record must contain a non-empty events array")
        if any(not isinstance(event, dict) for event in batch):
            raise ValueError("directory events must be JSON objects")
        if (record.get("first_sequence") != batch[0].get("sequence")
                or record.get("last_sequence") != batch[-1].get("sequence")):
            raise ValueError("directory event batch sequence bounds do not match")
        for event in batch:
            if not isinstance(event.get("sequence"), int):
                raise ValueError("directory event must have an integer sequence")
            if (previous_sequence is not None
                    and event["sequence"] <= previous_sequence):
                raise ValueError("directory event sequence is not increasing")
            previous_sequence = event["sequence"]
            events.append(event)
    return events
