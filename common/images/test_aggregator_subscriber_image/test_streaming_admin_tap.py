import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("envoy.data.tap.v3.wrapper_pb2")
MODULE_PATH = Path(__file__).with_name("streaming_admin_tap.py")
spec = importlib.util.spec_from_file_location("streaming_admin_tap", MODULE_PATH)
tap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tap)


def test_encode_varint_boundaries():
    assert tap.encode_varint(0) == b"\x00"
    assert tap.encode_varint(127) == b"\x7f"
    assert tap.encode_varint(128) == bytes([0x80, 0x01])
    assert tap.encode_varint(0xFFFFFFFF) == bytes([0xff, 0xff, 0xff, 0xff, 0x0f])


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
