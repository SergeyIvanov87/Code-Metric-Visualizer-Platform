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
    def __init__(self, event=None, broker_error=None):
        self._value = json.dumps(event).encode() if event is not None else None
        self._error = broker_error

    def error(self):
        return self._error

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


class BrokerError:
    def __init__(self, message, code=-195):
        self.message = message
        self._code = code

    def code(self):
        return self._code

    def __str__(self):
        return self.message


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

    received, terminal = aggregator.consume_capture(
        consumer, "events", "capture-1", tmp_path, 1
    )

    assert received == 1
    assert terminal.value() == event("capture_complete").value()
    assert not consumer.committed
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
    assert not consumer.committed

    aggregator.write_terminal_result(
        tmp_path,
        aggregator.CAPTURE_START_TIMEOUT_EXIT_CODE,
        "no capture data arrived",
    )
    assert (tmp_path / "result").read_text().strip() == "10"
    assert "no capture data" in (tmp_path / "result_log_stderr").read_text()


def test_retries_poll_errors_and_preserves_capture_flow(tmp_path, monkeypatch):
    sleeps = []
    consumer = Consumer([
        Message(broker_error=BrokerError("broker transport failed")),
        Message(broker_error=BrokerError("all brokers are down")),
        event("capture_complete"),
    ])
    monkeypatch.setattr(aggregator.time, "sleep", sleeps.append)

    received, _terminal = aggregator.consume_capture(
        consumer,
        "events",
        "capture-1",
        tmp_path,
        1,
        retry_backoff_seconds=0.25,
    )

    assert received == 0
    assert not consumer.committed
    assert sleeps == [0.25, 0.25]


def test_poll_fails_only_after_activity_deadline(monkeypatch):
    consumer = Consumer([
        Message(broker_error=BrokerError("down-1")),
        Message(broker_error=BrokerError("down-2")),
        Message(broker_error=BrokerError("down-3")),
    ])
    now = [0.0]

    def advancing_clock():
        now[0] += 0.2
        return now[0]

    monkeypatch.setattr(aggregator.time, "monotonic", advancing_clock)
    monkeypatch.setattr(aggregator.time, "sleep", lambda _seconds: None)

    with pytest.raises(TimeoutError, match="activity deadline"):
        aggregator.poll_until_deadline(consumer, deadline=1.0, backoff_seconds=0)


def test_successful_message_recalculates_activity_deadline(tmp_path, monkeypatch):
    class Clock:
        now = 0.0

    clock = Clock()

    class TimedConsumer(Consumer):
        def poll(self, timeout):
            clock.now += 0.75
            return super().poll(timeout)

    consumer = TimedConsumer([
        Message({"schema_version": 1, "type": "ignored", "capture_id": "other"}),
        event("capture_complete"),
    ])
    monkeypatch.setattr(aggregator.time, "monotonic", lambda: clock.now)

    received, _terminal = aggregator.consume_capture(
        consumer, "events", "capture-1", tmp_path, 1, retry_backoff_seconds=0
    )
    assert received == 0
    assert clock.now == 1.5


def test_reassembles_chunked_connection_log(tmp_path):
    consumer = Consumer([
        event(
            "connection_log_chunk",
            filename="sample.log",
            chunk_index=0,
            payload_base64=base64.b64encode(b"first ").decode(),
        ),
        event(
            "connection_log_chunk",
            filename="sample.log",
            chunk_index=1,
            payload_base64=base64.b64encode(b"second").decode(),
        ),
        event("connection_log_complete", filename="sample.log", chunk_count=2),
        event("capture_complete"),
    ])

    received, _terminal = aggregator.consume_capture(
        consumer, "events", "capture-1", tmp_path, 1
    )

    assert received == 1
    assert (tmp_path / "sample.log").read_bytes() == b"first second"


def test_retries_terminal_offset_commit(monkeypatch):
    class RecoveringCommitConsumer:
        def __init__(self):
            self.attempts = 0

        def commit(self, **_kwargs):
            self.attempts += 1
            if self.attempts < 3:
                raise RuntimeError("coordinator unavailable")

    consumer = RecoveringCommitConsumer()
    monkeypatch.setattr(aggregator.time, "sleep", lambda _seconds: None)

    aggregator.commit_until_deadline(
        consumer, object(), aggregator.time.monotonic() + 1, 0
    )

    assert consumer.attempts == 3


def test_reports_analyzer_artifacts_to_container_logs(tmp_path, capsys):
    (tmp_path / "result_log_stdout").write_text("analysis summary\n")
    (tmp_path / "result_log_stderr").write_text("inconsistent statistics\n")
    (tmp_path / "result").write_text("1\n")

    assert aggregator.report_analysis_result(tmp_path) == 1
    captured = capsys.readouterr()
    assert captured.out == "analysis summary\n"
    assert captured.err == "inconsistent statistics\n"


class EventuallyReadyBroker:
    def __init__(self, failures):
        self.failures = failures
        self.attempts = 0

    def list_topics(self, **_kwargs):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise RuntimeError("broker listener is not ready")


def test_waits_for_advertised_broker_listener(monkeypatch):
    broker = EventuallyReadyBroker(failures=2)
    monkeypatch.setattr(aggregator.time, "sleep", lambda _seconds: None)

    aggregator.wait_for_broker(broker, timeout_seconds=5)

    assert broker.attempts == 3


def test_broker_readiness_timeout_is_actionable():
    broker = EventuallyReadyBroker(failures=1)
    with pytest.raises(RuntimeError, match="not ready within 0 seconds"):
        aggregator.wait_for_broker(broker, timeout_seconds=0)
