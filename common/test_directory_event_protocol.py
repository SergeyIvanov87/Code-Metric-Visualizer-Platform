import io
import json

import pytest

from common.modules.directory_event_protocol import parse_directory_event_stream


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
