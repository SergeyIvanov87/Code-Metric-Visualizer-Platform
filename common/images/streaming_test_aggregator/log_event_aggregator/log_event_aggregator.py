#!/usr/bin/env python3
"""Consume decoded connection logs from Kafka and aggregate pytest results."""

import argparse
import base64
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from confluent_kafka import Consumer, KafkaError

SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")
CAPTURE_START_TIMEOUT_EXIT_CODE = 10


class CaptureStartTimeout(RuntimeError):
    pass


def safe_name(value):
    return SAFE_NAME.sub("_", value).strip("._") or "connection.log"


def write_terminal_result(result_directory, exit_code, message):
    (result_directory / "result_log_stdout").write_text("")
    (result_directory / "result_log_stderr").write_text(f"{message}\n")
    (result_directory / "result").write_text(f"{exit_code}\n")


def report_analysis_result(result_directory):
    """Mirror analyzer artifacts to container logs and return its exit code."""
    stdout = (result_directory / "result_log_stdout").read_text()
    stderr = (result_directory / "result_log_stderr").read_text()
    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n", flush=True)
    if stderr:
        print(
            stderr,
            end="" if stderr.endswith("\n") else "\n",
            file=sys.stderr,
            flush=True,
        )
    return int((result_directory / "result").read_text().strip())


def poll_until_deadline(consumer, deadline, backoff_seconds):
    """Poll through broker/network failures until the activity deadline."""
    last_error = None
    while time.monotonic() < deadline:
        try:
            remaining = deadline - time.monotonic()
            message = consumer.poll(min(1.0, max(0.0, remaining)))
        except Exception as error:
            kafka_error = error
        else:
            if message is None or not message.error():
                return message
            if message.error().code() == KafkaError._PARTITION_EOF:
                return None
            kafka_error = message.error()

        last_error = kafka_error
        print(
            f"Kafka poll failed; retrying until the activity deadline: {kafka_error}",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(min(backoff_seconds, max(0.0, deadline - time.monotonic())))
    detail = f": {last_error}" if last_error is not None else ""
    raise TimeoutError(f"Kafka poll did not recover before the activity deadline{detail}")


def commit_until_deadline(consumer, message, deadline, backoff_seconds):
    """Commit a terminal event despite a temporary broker/network outage."""
    last_error = None
    while time.monotonic() < deadline:
        try:
            consumer.commit(message=message, asynchronous=False)
            return
        except Exception as error:
            last_error = error
            print(
                f"Kafka commit failed; retrying until the activity deadline: {error}",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(min(backoff_seconds, max(0.0, deadline - time.monotonic())))
    raise TimeoutError(
        f"Kafka commit did not recover before the activity deadline: {last_error}"
    ) from last_error


def consume_capture(
    consumer,
    topic,
    capture_id,
    output_directory,
    timeout_seconds,
    retry_backoff_seconds=1.0,
):
    deadline = time.monotonic() + timeout_seconds
    received = 0
    while time.monotonic() < deadline:
        message = poll_until_deadline(consumer, deadline, retry_backoff_seconds)
        if message is None:
            continue
        # Any successfully consumed event proves that the producer/broker path
        # is alive. The configured timeout is an inactivity window, not a
        # lifetime limit for a healthy capture.
        deadline = time.monotonic() + timeout_seconds
        event = json.loads(message.value())
        if event.get("schema_version") != 1:
            raise ValueError("unsupported Kafka capture event schema_version")
        if event.get("capture_id") != capture_id:
            continue
        event_type = event.get("type")
        if event_type == "connection_log":
            filename = safe_name(event["filename"])
            payload = base64.b64decode(event["payload_base64"], validate=True)
            temporary = output_directory / f".{filename}.tmp"
            temporary.write_bytes(payload)
            temporary.replace(output_directory / filename)
            received += 1
        elif event_type == "capture_complete":
            commit_until_deadline(consumer, message, deadline, retry_backoff_seconds)
            return received
        elif event_type == "capture_start_timeout":
            commit_until_deadline(consumer, message, deadline, retry_backoff_seconds)
            wait_msec = event.get("wait_msec", "unknown")
            raise CaptureStartTimeout(
                f"no capture data arrived during the {wait_msec} ms initialization interval"
            )
        elif event_type == "capture_failed":
            raise RuntimeError(event.get("error", "tap subscriber reported failure"))
        else:
            raise ValueError(f"unsupported Kafka capture event type: {event_type!r}")
    raise TimeoutError(f"timed out waiting for capture {capture_id!r} to complete")



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
    parser.add_argument("--brokers", required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--broker-startup-timeout-seconds", type=int, default=120)
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--capture-id", required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--result-directory", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--consumer-retry-backoff-seconds", type=float, default=1.0)
    parser.add_argument("--ready-file", type=Path)
    args = parser.parse_args()
    if args.consumer_retry_backoff_seconds < 0:
        parser.error("--consumer-retry-backoff-seconds must not be negative")
    args.output_directory.mkdir(parents=True, exist_ok=True)
    args.result_directory.mkdir(parents=True, exist_ok=True)

    consumer = Consumer({
        "bootstrap.servers": args.brokers,
        "group.id": args.group_id,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })
    try:
        wait_for_broker(consumer, args.broker_startup_timeout_seconds)
        consumer.subscribe([args.topic])
        if args.ready_file:
            args.ready_file.touch()
        try:
            received = consume_capture(
                consumer,
                args.topic,
                args.capture_id,
                args.output_directory,
                args.timeout_seconds,
                args.consumer_retry_backoff_seconds,
            )
        except CaptureStartTimeout as error:
            write_terminal_result(
                args.result_directory, CAPTURE_START_TIMEOUT_EXIT_CODE, error
            )
            return CAPTURE_START_TIMEOUT_EXIT_CODE
    finally:
        consumer.close()

    if received == 0:
        raise RuntimeError("capture completed without any connection logs")
    subprocess.run(
        [
            "/package/log_watcher_service.sh",
            str(args.output_directory),
            "1",
            str(args.result_directory),
        ],
        check=False,
    )
    return report_analysis_result(args.result_directory)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(error, file=sys.stderr)
        sys.exit(255)
