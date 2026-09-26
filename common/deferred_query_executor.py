#!/usr/bin/env python3
"""Own the upload, processor, result publication, and cleanup lifecycle."""

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

CHUNK_SIZE = 64 * 1024
MAX_RESULT_BYTES = 1024 * 1024
stopping = False
processor = None


def request_stop(_signal, _frame):
    global stopping
    stopping = True


def prepare_api_channel(processor_path, request_directory):
    """Let the processor create its input FIFO and add our result FIFO."""
    prepared = subprocess.run(
        [processor_path, "--request-directory", str(request_directory),
         "--prepare-api-channel"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5,
    )
    if prepared.returncode:
        detail = prepared.stderr.strip() or prepared.stdout.strip()
        raise RuntimeError(f"processor API-channel preparation failed: {detail}")
    report = json.loads(prepared.stdout)
    result_fifo = request_directory / "async_result"
    os.mkfifo(result_fifo, 0o640)
    report["result"] = str(result_fifo)
    report["result_type"] = "FIFO"
    return report, result_fifo


def run_processor(command, result_path):
    """Run a FIFO-aware processor and capture its bounded result."""
    global processor
    processor = subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    oversized = False
    captured = 0
    with result_path.open("wb") as result:
        while not stopping:
            chunk = processor.stdout.read(CHUNK_SIZE)
            if not chunk:
                break
            available = MAX_RESULT_BYTES - captured
            if available:
                result.write(chunk[:available])
                captured += min(len(chunk), available)
            if len(chunk) > available:
                oversized = True
                processor.terminate()
                break
    if processor.poll() is None and (stopping or oversized):
        processor.terminate()
    try:
        return_code = processor.wait(timeout=2)
    except subprocess.TimeoutExpired:
        processor.kill()
        return_code = processor.wait()
    processor.stdout.close()
    processor = None
    if oversized:
        result_path.write_bytes(b"processor output exceeded 1048576 bytes\n")
    return return_code != 124


def publish(result_fifo, result_path, timeout):
    deadline = time.monotonic() + timeout
    descriptor = None
    try:
        while not stopping and time.monotonic() < deadline:
            try:
                descriptor = os.open(result_fifo, os.O_WRONLY | os.O_NONBLOCK)
                break
            except OSError:
                time.sleep(0.02)
        if descriptor is None:
            return False
        with result_path.open("rb") as result:
            while not stopping:
                chunk = result.read(CHUNK_SIZE)
                if not chunk:
                    return True
                view = memoryview(chunk)
                while view and time.monotonic() < deadline:
                    try:
                        written = os.write(descriptor, view)
                        view = view[written:]
                    except BlockingIOError:
                        time.sleep(0.02)
                if view:
                    return False
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return False


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--processor", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--initial-timeout", required=True, type=float)
    parser.add_argument("--update-timeout", required=True, type=float)
    parser.add_argument("--result-timeout", required=True, type=float)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--readiness-fd", required=True, type=int)
    parser.add_argument("--session-lock", required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    arguments = options.arguments[1:] if options.arguments[:1] == ["--"] else options.arguments
    request_directory = Path(options.input)
    # Processor output is staged separately and capped by run_processor. It can
    # then wait for a client to open async_result without blocking the processor
    # or keeping it alive for the result-consumption timeout.
    result_path = request_directory / "processor_result"
    try:
        (request_directory / "executor.json").write_text(json.dumps({
            "pid": os.getpid(), "session_id": options.session_id,
            "session_lock": options.session_lock,
        }))
        report, result_fifo = prepare_api_channel(
            options.processor, request_directory
        )
        readiness = json.dumps(report).encode() + b"\n"
        os.write(options.readiness_fd, readiness)
        os.close(options.readiness_fd)
        complete = run_processor([
            options.processor,
            "--request-directory", str(request_directory),
            "--initial-timeout", str(options.initial_timeout),
            "--update-timeout", str(options.update_timeout),
            "--", *arguments,
        ], result_path)
        if complete and not stopping:
            publish(result_fifo, result_path, options.result_timeout)
        return 0
    finally:
        if processor is not None and processor.poll() is None:
            processor.terminate()
        shutil.rmtree(request_directory, ignore_errors=True)
        try:
            Path(options.session_lock).rmdir()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    for handled_signal in (signal.SIGINT, signal.SIGTERM):
        signal.signal(handled_signal, request_stop)
    raise SystemExit(main())
