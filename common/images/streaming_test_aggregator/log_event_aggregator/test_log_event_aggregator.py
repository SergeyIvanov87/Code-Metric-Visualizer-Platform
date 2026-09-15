import base64
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

fake_module = types.ModuleType("confluent_kafka")
fake_module.Consumer = object
fake_module.KafkaError = types.SimpleNamespace(_PARTITION_EOF=-191)
sys.modules.setdefault("confluent_kafka", fake_module)
module_path = Path(__file__).with_name("log_event_aggregator.py")
spec = importlib.util.spec_from_file_location("log_event_aggregator", module_path)
aggregator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aggregator)


class Message:
    def __init__(self, event):
        self._value = json.dumps(event).encode()

    def error(self):
        return None

    def value(self):
        return self._value


class Consumer:
    def __init__(self, events):
        self.events = iter(events)
        self.committed = False

    def poll(self, _timeout):
        return next(self.events, None)

    def commit(self, **_kwargs):
        self.committed = True


def event(event_type, **values):
    return Message({"schema_version": 1, "type": event_type, "capture_id": "capture-1", **values})


def test_consumes_logs_until_capture_complete(tmp_path):
    payload = b"<14>Sep 15 12:00:00 sample-tester[1]: collected 1 item\n"
    consumer = Consumer([
        event(
            "connection_log",
            filename="sample-tester__connection_1.log",
            payload_base64=base64.b64encode(payload).decode(),
        ),
        event("capture_complete"),
    ])

    received = aggregator.consume_capture(
        consumer, "events", "capture-1", tmp_path, 1
    )

    assert received == 1
    assert consumer.committed
    assert (tmp_path / "sample-tester__connection_1.log").read_bytes() == payload


def test_rejects_unsafe_filename_parts():
    assert aggregator.safe_name("../../a tester.log") == "a_tester.log"


def test_capture_failure_is_not_interpreted_as_test_result(tmp_path):
    consumer = Consumer([event("capture_failed", error="tap disconnected")])
    with pytest.raises(RuntimeError, match="tap disconnected"):
        aggregator.consume_capture(consumer, "events", "capture-1", tmp_path, 1)


def test_capture_start_timeout_has_distinguishable_result(tmp_path):
    consumer = Consumer([
        event("capture_start_timeout", wait_msec=60000, exit_code=10)
    ])
    with pytest.raises(aggregator.CaptureStartTimeout, match="60000 ms"):
        aggregator.consume_capture(consumer, "events", "capture-1", tmp_path, 1)
    assert consumer.committed

    aggregator.write_terminal_result(
        tmp_path,
        aggregator.CAPTURE_START_TIMEOUT_EXIT_CODE,
        "no capture data arrived",
    )
    assert (tmp_path / "result").read_text().strip() == "10"
    assert "no capture data" in (tmp_path / "result_log_stderr").read_text()
