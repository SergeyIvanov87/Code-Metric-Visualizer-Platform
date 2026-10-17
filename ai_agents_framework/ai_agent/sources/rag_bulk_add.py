#!/usr/bin/env python3
"""Bridge streaming-directory upload events to the regular RAG add query."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from queue import Queue
import re
import signal
from threading import Lock, Thread
import time
from uuid import uuid4

from directory_event_protocol import iter_directory_event_stream
from doc_type_association import document_type
from fs_api_wrappers import (
    augmented_metadata,
    create_api_query_interruptible,
    get_normalized_api_queries,
    rag_add_file,
    start_uploader,
)

DEFAULTS = {
    "metadata": "", "WaitInitialQueryTimeoutSec": "60",
    "WaitQueryUpdateTimeoutSec": "10", "WaitResultConsumptionTimeoutSec": "60",
    "SESSION_ID": "default", "workers": "4",
}
MAX_WORKERS = 32
EVENT_RETRY_INTERVAL = 0.05
API_SERVICE_NAME = "api.pmccabe_collector.restapi.org"
API_QUERY_PATTERNS = {
    "streaming_directory_events": re.compile(
        r".*file-uploader_streaming_directory_events.*"
    ),
    "rag_add": re.compile(r".*ai_agent_rag_add_doc.*"),
}

stopping = False
TERMINATE_WORKER = object()
TERMINATE_COLLECTOR = object()


def stop(_signal, _frame):
    global stopping
    stopping = True


def values(arguments):
    if len(arguments) % 2:
        raise ValueError("query arguments must be name/value pairs")
    result = dict(DEFAULTS)
    for index in range(0, len(arguments), 2):
        name = arguments[index].lstrip("-")
        if name not in DEFAULTS:
            raise ValueError(f"unsupported query parameter: {arguments[index]}")
        result[name] = arguments[index + 1]
    if not re.fullmatch(r"[A-Za-z0-9_.:@+-]{1,128}", result["SESSION_ID"]):
        raise ValueError("SESSION_ID must contain 1-128 safe characters")
    try:
        workers = int(result["workers"])
    except (TypeError, ValueError):
        raise ValueError("workers must be an integer") from None
    try:
        max_workers = int(os.environ.get("MAX_WORKERS", str(MAX_WORKERS)))
    except ValueError:
        raise ValueError("MAX_WORKERS must be a positive integer") from None
    if max_workers <= 0:
        raise ValueError(f"MAX_WORKERS must be a positive integer, got: {max_workers}")
    if not 1 <= workers <= max_workers:
        raise ValueError(f"workers must be between 1 and {max_workers}, got: {workers}")
    return result


def completion_timestamp():
    """Return the current UTC time in an ISO 8601 JSON-friendly form."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def prepare(request, config, uploader_query, uploader_session_id):
    report = start_uploader(
        uploader_query, request, config, uploader_session_id
    )
    stage = Path(report["staging"]).resolve(strict=True)
    input_path = request / "input"
    input_path.symlink_to(os.path.relpath(stage, request), target_is_directory=True)
    events = request / "events"
    os.mkfifo(events, 0o644)
    events.chmod(0o644)
    return {
        "input": str(input_path), "input_type": "DIRECTORY",
        "staging": str(stage),
        "events": str(events), "events_type": "FIFO",
        "protocol": "cmvp.rag-bulk-events.v1",
        "uploader_request": str(Path(report["events"]).parent),
    }


def publish_event(descriptor, event, timeout=1):
    payload = json.dumps(event, separators=(",", ":")).encode() + b"\n"
    deadline = time.monotonic() + timeout
    while not stopping and time.monotonic() < deadline:
        try:
            if descriptor[0] is None:
                descriptor[0] = os.open(descriptor[1], os.O_WRONLY | os.O_NONBLOCK)
            os.write(descriptor[0], payload)
            return True
        except OSError:
            if descriptor[0] is not None:
                os.close(descriptor[0])
                descriptor[0] = None
            time.sleep(0.05)
    return False


def add_file_worker(
    rag_add_query, session_id, config, stage, input_queue, outcome_queue
):
    """Process queued files until this worker receives its termination marker."""
    while True:
        task = input_queue.get()
        try:
            if task is TERMINATE_WORKER:
                return
            event, sequence = task
            try:
                outcome = rag_add_file(
                    rag_add_query,
                    session_id,
                    config,
                    stage,
                    event["path"],
                    sequence,
                )
            except Exception as error:
                outcome = {
                    "sequence": sequence, "status": "failed",
                    "path": event.get("path", ""), "doc_id": "",
                    "error": str(error), "timestamp": completion_timestamp(),
                }
            if "timestamp" not in outcome:
                outcome["timestamp"] = completion_timestamp()
            outcome_queue.put(outcome)
        finally:
            input_queue.task_done()


def collect_outcomes(outcome_queue, added, failed, writer):
    """Publish worker results as they arrive, retrying the current result."""
    while True:
        outcome = outcome_queue.get()
        if outcome is TERMINATE_COLLECTOR:
            outcome_queue.task_done()
            return
        while not publish_event(writer, outcome, timeout=EVENT_RETRY_INTERVAL):
            time.sleep(EVENT_RETRY_INTERVAL)
        (added if outcome["status"] == "added" else failed).append(outcome)
        outcome_queue.task_done()


def stop_workers(worker_threads, input_queues):
    """Stop and join the queues and worker threads that successfully started."""
    active_queues = input_queues[:len(worker_threads)]
    for input_queue in active_queues:
        input_queue.put(TERMINATE_WORKER)
    for input_queue in active_queues:
        input_queue.join()
    for worker in worker_threads:
        worker.join()


def start_workers(worker_threads, input_queues):
    """Start workers and clean up the started prefix if startup fails."""
    started = []
    try:
        for worker in worker_threads:
            worker.start()
            started.append(worker)
    except Exception:
        stop_workers(started, input_queues)
        raise
    return started


def run(options, config, rag_add_queries):
    report = json.loads((options.request_directory / "stage.json").read_text())
    uploader = json.loads((options.request_directory / "uploader.json").read_text())
    stage = Path(report["staging"])
    writer = [None, Path(report["events"])]
    added, failed = [], []
    worker_count = int(config["workers"])
    input_queues = [Queue() for _ in range(worker_count)]
    outcome_queue = Queue()
    worker_threads = [
        Thread(
            target=add_file_worker,
            args=(
                rag_add_queries[index][0],
                rag_add_queries[index][1],
                config,
                stage,
                input_queue,
                outcome_queue,
            ),
            name=f"rag-bulk-add-{index + 1}",
        )
        for index, input_queue in enumerate(input_queues)
    ]
    collector = Thread(
        target=collect_outcomes,
        args=(outcome_queue, added, failed, writer),
        name="rag-bulk-add-collector",
    )
    started_workers = start_workers(worker_threads, input_queues)
    collector_started = False
    sequence = 0
    sequence_lock = Lock()
    try:
        collector.start()
        collector_started = True
        with Path(uploader["events"]).open() as stream:
            for event in iter_directory_event_stream(stream):
                if event.get("status") != "ready":
                    continue
                with sequence_lock:
                    sequence += 1
                    task_sequence = sequence
                input_queues[(task_sequence - 1) % worker_count].put(
                    (event, task_sequence)
                )
    finally:
        stop_workers(started_workers, input_queues)
        if collector_started:
            outcome_queue.put(TERMINATE_COLLECTOR)
            outcome_queue.join()
            collector.join()
    timestamp = completion_timestamp()
    terminal = {"sequence": sequence + 1, "status": "terminated",
                "added_count": len(added), "failed_count": len(failed),
                "timestamp": timestamp}
    publish_event(writer, terminal)
    if writer[0] is not None:
        os.close(writer[0])
    print(json.dumps({"error_code": "0" if not failed else "1",
                      "timestamp": timestamp, "added": added, "failed": failed},
                     separators=(",", ":")))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-directory", required=True, type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check-arguments", action="store_true")
    modes.add_argument("--prepare-api-channel", action="store_true")
    parser.add_argument("--initial-timeout", type=float)
    parser.add_argument("--update-timeout", type=float)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    arguments = options.arguments[1:] if options.arguments[:1] == ["--"] else options.arguments
    try:
        config = values(arguments)
        if options.check_arguments:
            print('{"error_code":"0","error_description":""}')
            return 0
        shared_api_dir = os.environ.get("SHARED_API_DIR", "/api")
        normalized_api_queries = get_normalized_api_queries(
            shared_api_dir,
            API_SERVICE_NAME,
            API_QUERY_PATTERNS,
        )
        if options.prepare_api_channel:
            uploader_session_id = (
                f"rag-bulk-{config['SESSION_ID']}-{uuid4().hex}"
            )
            uploader_query = create_api_query_interruptible(
                shared_api_dir,
                normalized_api_queries["streaming_directory_events"],
                uploader_session_id,
            )
            report = prepare(
                options.request_directory.resolve(strict=True),
                config,
                uploader_query,
                uploader_session_id,
            )
            (options.request_directory / "stage.json").write_text(json.dumps(report))
            print(json.dumps(report))
            return 0
        config["RUN_ID"] = uuid4().hex
        rag_add_queries = []
        for worker_index in range(int(config["workers"])):
            session_id = (
                f"rag-bulk-add-{config['SESSION_ID']}-{config['RUN_ID']}-"
                f"worker-{worker_index + 1}"
            )
            query = create_api_query_interruptible(
                shared_api_dir,
                normalized_api_queries["rag_add"],
                session_id,
            )
            rag_add_queries.append((query, session_id))
        return run(options, config, rag_add_queries)
    except Exception as error:
        print(json.dumps({
            "error_code": "1", "error_description": str(error),
            "timestamp": completion_timestamp(),
        }))
        return 1


if __name__ == "__main__":
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    raise SystemExit(main())
