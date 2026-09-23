#!/usr/bin/env python3
"""Allocate a deferred pseudo-filesystem request and start its owner."""

import argparse
import base64
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


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
    request_directory = Path(tempfile.mkdtemp(prefix=f"deferred-{session_token}-", dir=api_directory))
    input_path = request_directory / "input"
    os.mkfifo(input_path, 0o620)
    read_fd, write_fd = os.pipe()
    command = [
        str(executor), "--processor", str(processor), "--input", str(input_path),
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
        import select
        ready, _, _ = select.select([read_fd], [], [], options.readiness_timeout)
        message = os.read(read_fd, 32) if ready else b""
        if message != b"READY\n" or child.poll() is not None:
            child.terminate()
            raise RuntimeError("deferred executor did not become ready")
        print(input_path)
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
            os.close(read_fd)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
