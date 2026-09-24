#!/usr/bin/env python3
"""Own the upload, processor, result publication, and cleanup lifecycle."""

import argparse
import json
import os
from pathlib import Path
import selectors
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


def receive(input_path, output, initial_timeout, update_timeout):
    descriptor = os.open(input_path, os.O_RDONLY | os.O_NONBLOCK)
    selector = selectors.DefaultSelector()
    selector.register(descriptor, selectors.EVENT_READ)
    started = False
    deadline = time.monotonic() + initial_timeout
    try:
        while not stopping:
            remaining = max(0, deadline - time.monotonic())
            events = selector.select(remaining)
            if not events:
                return started
            chunk = os.read(descriptor, CHUNK_SIZE)
            if chunk:
                output.write(chunk)
                output.flush()
                started = True
                deadline = time.monotonic() + update_timeout
            elif started:
                return True
            else:
                # No writer is connected yet. Avoid a busy loop while preserving
                # the initial-silence deadline.
                time.sleep(min(0.02, remaining))
    finally:
        selector.close()
        os.close(descriptor)
    return False


def run_processor(command, upload, result_path):
    global processor
    oversized = False
    captured = 0
    with upload.open("rb") as source, result_path.open("wb") as result:
        processor = subprocess.Popen(
            command, stdin=source, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        selector = selectors.DefaultSelector()
        selector.register(processor.stdout, selectors.EVENT_READ)
        while not stopping:
            events = selector.select(0.05)
            if events:
                chunk = os.read(processor.stdout.fileno(), CHUNK_SIZE)
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
            elif processor.poll() is not None:
                break
        selector.close()
        if processor.poll() is None and (stopping or oversized):
            processor.terminate()
        try:
            processor.wait(timeout=2)
        except subprocess.TimeoutExpired:
            processor.kill()
            processor.wait()
        # stdout is a pipe, so the child can never place more than the bounded
        # kernel pipe capacity beyond the bytes accepted above.
        processor.stdout.close()
    processor = None
    if oversized:
        result_path.write_bytes(b"processor output exceeded 1048576 bytes\n")


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
    input_path = request_directory / "input"
    result_fifo = request_directory / "async_result"
    # The input FIFO cannot be passed directly to a processor that starts only
    # after the upload is complete. This regular staging file preserves the
    # received bytes until run_processor opens them as the processor's stdin.
    upload_path = request_directory / "upload"
    # Processor output is staged separately and capped by run_processor. It can
    # then wait for a client to open async_result without blocking the processor
    # or keeping it alive for the result-consumption timeout.
    result_path = request_directory / "processor_result"
    try:
        os.mkfifo(input_path, 0o620)
        os.mkfifo(result_fifo, 0o640)
        (request_directory / "executor.json").write_text(json.dumps({
            "pid": os.getpid(), "session_id": options.session_id,
            "session_lock": options.session_lock,
        }))
        readiness = b"READY\n" + os.fsencode(input_path) + b"\n"
        os.write(options.readiness_fd, readiness)
        os.close(options.readiness_fd)
        with upload_path.open("wb") as upload:
            complete = receive(input_path, upload, options.initial_timeout, options.update_timeout)
        if complete and not stopping:
            run_processor([options.processor, *arguments], upload_path, result_path)
            if not stopping:
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
