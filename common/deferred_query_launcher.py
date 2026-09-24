#!/usr/bin/env python3
"""Allocate a deferred pseudo-filesystem request and start its owner."""

import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


TIMEOUT_ARGUMENTS = {
    "WaitInitialQueryTimeoutSec": "initial_timeout",
    "WaitQueryUpdateTimeoutSec": "update_timeout",
    "WaitResultConsumptionTimeoutSec": "result_timeout",
}
SESSION_PATTERN = re.compile(r"^[A-Za-z0-9_.:@+-]{1,128}$")


def resolved_options(arguments):
    """Return and validate transport options embedded in resolved query argv."""
    values = {}
    index = 0
    while index < len(arguments):
        name = arguments[index].lstrip("-")
        if name in (*TIMEOUT_ARGUMENTS, "SESSION_ID"):
            if index + 1 >= len(arguments):
                raise ValueError(f"missing value for {arguments[index]}")
            values[name] = arguments[index + 1]
            index += 2
        else:
            index += 1

    session = values.get("SESSION_ID", "")
    if not SESSION_PATTERN.fullmatch(session):
        raise ValueError("SESSION_ID must contain 1-128 safe characters")
    result = {"session_id": session}
    for query_name, destination in TIMEOUT_ARGUMENTS.items():
        try:
            value = float(values[query_name])
        except (KeyError, ValueError):
            raise ValueError(f"{query_name} must be a number") from None
        if not 0 < value <= 86400:
            raise ValueError(f"{query_name} must be greater than 0 and at most 86400")
        result[destination] = value
    return result


def encoded_session(session):
    return base64.urlsafe_b64encode(session.encode()).decode().rstrip("=")


def read_readiness(descriptor, timeout):
    """Read the processor's JSON API-channel report from the executor."""
    import select

    deadline = time.monotonic() + timeout
    message = bytearray()
    while b"\n" not in message:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        ready, _, _ = select.select([descriptor], [], [], remaining)
        if not ready:
            break
        chunk = os.read(descriptor, 4096)
        if not chunk:
            break
        message.extend(chunk)
    line, separator, remainder = bytes(message).partition(b"\n")
    if not separator or remainder:
        raise ValueError("incomplete executor readiness report")
    report = json.loads(os.fsdecode(line))
    if not isinstance(report, dict):
        raise ValueError("executor readiness report must be a JSON object")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-directory", required=True)
    parser.add_argument("--processor", required=True)
    parser.add_argument("--executor", default=str(Path(__file__).with_name("deferred_query_executor.py")))
    parser.add_argument("--readiness-timeout", type=float, default=5)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    query_arguments = options.arguments[1:] if options.arguments[:1] == ["--"] else options.arguments

    try:
        transport = resolved_options(query_arguments)
        api_directory = Path(options.api_directory).resolve(strict=True)
        processor = Path(options.processor).resolve(strict=True)
        executor = Path(options.executor).resolve(strict=True)
        if not api_directory.is_dir():
            raise ValueError("API directory is not a directory")
        for label, executable in (("processor", processor), ("executor", executor)):
            if not executable.is_file() or not os.access(executable, os.X_OK):
                raise ValueError(f"{label} is not executable: {executable}")
        argument_check = subprocess.run(
            [str(processor), "--check-arguments", *query_arguments],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5,
        )
        if argument_check.returncode:
            detail = argument_check.stdout.strip() or argument_check.stderr.strip()
            raise ValueError(f"processor argument validation failed: {detail}")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.error(str(error))

    session_token = encoded_session(transport["session_id"])
    session_lock = api_directory / f".deferred-session-{session_token}"
    try:
        session_lock.mkdir(mode=0o700)
    except FileExistsError:
        parser.error(f"SESSION_ID is already active: {transport['session_id']}")
    request_directory = Path(tempfile.mkdtemp(
        prefix=f"deferred-{session_token}-", dir=api_directory
    ))
    # mkdtemp creates the directory atomically. Verify its location before any
    # FIFO path can be published; this also makes a bad/missing API mount fail
    # synchronously instead of looking like a disappearing deferred request.
    if request_directory.parent != api_directory or not request_directory.is_dir():
        raise RuntimeError(f"failed to create request directory below {api_directory}")
    read_fd, write_fd = os.pipe()
    command = [
        str(executor), "--processor", str(processor), "--input", str(request_directory),
        "--initial-timeout", str(transport["initial_timeout"]),
        "--update-timeout", str(transport["update_timeout"]),
        "--result-timeout", str(transport["result_timeout"]),
        "--session-id", transport["session_id"], "--readiness-fd", str(write_fd),
        "--session-lock", str(session_lock),
        "--", *query_arguments,
    ]
    try:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True,
                                 close_fds=True, pass_fds=(write_fd,))
        os.close(write_fd)
        report = read_readiness(read_fd, options.readiness_timeout)
        input_path = Path(report["input_FIFO"])
        result_path = Path(report["result_FIFO"])
        expected_input_path = request_directory / "input"
        expected_result_path = request_directory / "async_result"
        if (set(report) != {"input_FIFO", "result_FIFO"}
                or input_path != expected_input_path
                or result_path != expected_result_path
                or child.poll() is not None
                or not input_path.is_fifo() or not result_path.is_fifo()):
            child.terminate()
            raise RuntimeError("deferred executor did not become ready")
        print(json.dumps(report))
        return 0
    except Exception as error:
        import shutil
        shutil.rmtree(request_directory, ignore_errors=True)
        try:
            session_lock.rmdir()
        except FileNotFoundError:
            pass
        print(f"deferred request allocation failed: {error}", file=sys.stderr)
        return 1
    finally:
        try:
            os.close(write_fd)
        except OSError:
            pass
        try:
            os.close(read_fd)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
