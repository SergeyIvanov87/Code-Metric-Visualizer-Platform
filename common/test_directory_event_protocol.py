import io
import json

import pytest

from common.modules.directory_event_protocol import (
    iter_directory_event_stream,
    parse_directory_event_stream,
)


def line(events):
    return json.dumps({
        "first_sequence": events[0]["sequence"],
        "last_sequence": events[-1]["sequence"],
        "events": events,
    }).encode() + b"\n"


def test_parse_directory_event_stream_flattens_batches_and_terminal_event():
    ready = [
        {"sequence": 1, "status": "ready", "path": "one.txt"},
        {"sequence": 2, "status": "ready", "path": "nested/two.txt"},
    ]
    terminal = [{"sequence": 3, "status": "terminated"}]
    stream = io.BytesIO(
        line(ready) + line(terminal)
        + b'{"type":"transport_closed","reason":"request cleanup"}\n'
    )

    assert parse_directory_event_stream(stream) == ready + terminal


def test_parse_directory_event_stream_rejects_invalid_sequence_bounds():
    stream = io.StringIO(
        '{"first_sequence":2,"last_sequence":2,'
        '"events":[{"sequence":1,"status":"ready"}]}\n'
    )

    with pytest.raises(ValueError, match="sequence bounds"):
        parse_directory_event_stream(stream)


def test_iter_directory_event_stream_yields_before_reading_the_next_batch():
    ready = [
        {"sequence": 1, "status": "ready", "path": "one.txt"},
        {"sequence": 2, "status": "ready", "path": "two.txt"},
    ]
    terminal = [{"sequence": 3, "status": "terminated"}]

    class ObservedStream:
        def __init__(self):
            self.lines = iter((line(ready), line(terminal)))
            self.lines_read = 0

        def __iter__(self):
            return self

        def __next__(self):
            value = next(self.lines)
            self.lines_read += 1
            return value

    stream = ObservedStream()
    events = iter_directory_event_stream(stream)

    assert next(events) == ready[0]
    assert next(events) == ready[1]
    assert stream.lines_read == 1
    assert next(events) == terminal[0]
    assert stream.lines_read == 2
