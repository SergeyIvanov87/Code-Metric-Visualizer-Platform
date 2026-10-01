#!/usr/bin/env python3
"""Observe completed files on shared staging and deliver journaled event batches."""

import argparse
from collections import deque
import errno
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import time

MAX_PATH_BYTES = 1024
MAX_DEPTH = 64
MAX_FILES = 10000
MAX_TOTAL_BYTES = 100 * 1024 * 1024 * 1024
SCAN_INTERVAL = 0.05
DEFAULT_DIR_SKIP_REGEX = r"(?:^|.*/)(?:[.][^/]+|__pycache__|__pypackages__|node_modules)"
stopping = False


def stop(_signal, _frame):
    global stopping
    stopping = True


def value_of(arguments, name, default=None):
    for index in range(0, len(arguments) - 1, 2):
        if arguments[index].lstrip("-") == name:
            return arguments[index + 1]
    if default is not None:
        return default
    raise ValueError(f"missing {name}")


def regex_value(arguments, name, default):
    text = value_of(arguments, name, default)
    if len(text) > 1024:
        raise ValueError(f"{name} exceeds 1024 characters")
    try:
        return re.compile(text)
    except re.error as error:
        raise ValueError(f"invalid {name}: {error}") from None


def validate(arguments):
    patterns = (
        regex_value(arguments, "file_allow_regex", ".*"),
        regex_value(arguments, "file_skip_regex", r"(?!)"),
        regex_value(arguments, "dir_allow_regex", ".*"),
        regex_value(arguments, "dir_skip_regex", DEFAULT_DIR_SKIP_REGEX),
    )
    session = value_of(arguments, "SESSION_ID", "default")
    if not re.fullmatch(r"[A-Za-z0-9_.:@+-]{1,128}", session):
        raise ValueError("SESSION_ID must contain 1-128 safe characters")
    try:
        result_timeout = float(value_of(
            arguments, "WaitResultConsumptionTimeoutSec", "60",
        ))
    except ValueError:
        raise ValueError("WaitResultConsumptionTimeoutSec must be a number") from None
    if not 0 < result_timeout <= 86400:
        raise ValueError(
            "WaitResultConsumptionTimeoutSec must be greater than 0 and at most 86400"
        )
    return patterns, session, result_timeout


def staging_root(request):
    """Return staging beside deferred requests on their shared API volume."""
    root = request.parent / ".staging"
    root.mkdir(mode=0o2770, exist_ok=True)
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("shared staging root is not a directory")
    return root


def prepare(request, arguments):
    _, session, _ = validate(arguments)
    request = request.resolve(strict=True)
    root = staging_root(request)
    stage = root / f"events-{session}-{request.name}"
    stage.mkdir(mode=0o2770)
    if stage.resolve(strict=True).parent != root:
        raise ValueError("shared staging directory escaped its configured root")
    input_path = request / "input"
    input_path.symlink_to(
        os.path.relpath(stage, start=request), target_is_directory=True,
    )
    if (not input_path.is_symlink()
            or input_path.resolve(strict=True) != stage.resolve(strict=True)):
        raise ValueError("input link does not resolve to shared staging")
    events_fifo = request / "events"
    os.mkfifo(events_fifo, 0o640)
    return {
        "input": str(input_path), "input_type": "DIRECTORY",
        "staging": str(stage), "staging_type": "DIRECTORY",
        "events": str(events_fifo), "events_type": "FIFO",
        "protocol": "cmvp.directory-events.v1",
    }


def safe_relative(stage, path):
    relative = path.relative_to(stage)
    text = PurePosixPath(*relative.parts).as_posix()
    if (not text or ".." in relative.parts or len(relative.parts) > MAX_DEPTH
            or len(os.fsencode(text)) > MAX_PATH_BYTES):
        raise ValueError(f"unsafe relative path: {text!r}")
    return text


def scan(stage, patterns):
    file_allow, file_skip, dir_allow, dir_skip = patterns
    found = {}
    for root, directories, files in os.walk(stage, followlinks=False):
        root_path = Path(root)
        for name in directories[:]:
            node = root_path / name
            relative = safe_relative(stage, node)
            try:
                info = node.lstat()
            except FileNotFoundError:
                directories.remove(name)
                continue
            allowed = (stat.S_ISDIR(info.st_mode)
                       and dir_allow.fullmatch(relative)
                       and not dir_skip.fullmatch(relative))
            if not allowed:
                directories.remove(name)
        for name in files:
            node = root_path / name
            relative = safe_relative(stage, node)
            try:
                info = node.lstat()
            except FileNotFoundError:
                continue
            if (stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                    and file_allow.fullmatch(relative)
                    and not file_skip.fullmatch(relative)):
                found[relative] = (
                    info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                )
    if len(found) > MAX_FILES or sum(item[2] for item in found.values()) > MAX_TOTAL_BYTES:
        raise ValueError("shared staging admission limit exceeded")
    return found


def write_batch(result_fifo, events):
    try:
        descriptor = os.open(result_fifo, os.O_WRONLY | os.O_NONBLOCK)
    except OSError as error:
        if error.errno == errno.ENXIO:
            return False
        raise
    payload = json.dumps({
        "first_sequence": events[0]["sequence"],
        "last_sequence": events[-1]["sequence"],
        "events": events,
    }, separators=(",", ":")).encode() + b"\n"
    try:
        offset = 0
        while offset < len(payload) and not stopping:
            try:
                offset += os.write(descriptor, payload[offset:])
            except BlockingIOError:
                time.sleep(0.01)
        return offset == len(payload)
    except BrokenPipeError:
        return False
    finally:
        os.close(descriptor)


def run(options, arguments):
    patterns, session, result_timeout = validate(arguments)
    request = options.request_directory.resolve(strict=True)
    report_path = request / "stage.json"
    if report_path.exists():
        report = json.loads(report_path.read_text())
        stage = Path(report["staging"]).resolve(strict=True)
        input_path = Path(report["input"])
        if (not input_path.is_symlink()
                or input_path.resolve(strict=True) != stage):
            raise ValueError("input link no longer resolves to shared staging")
    else:
        # The executor records the preparation report for independently invoked tests.
        candidates = sorted(staging_root(request).glob(f"events-*-{request.name}"))
        if len(candidates) != 1:
            raise ValueError("prepared shared staging directory not found")
        stage = candidates[0]
    events_fifo = request / "events"
    if not events_fifo.is_fifo():
        raise ValueError("prepared events channel is not a FIFO")
    journal = request / "event_journal.jsonl"
    previous = {}
    emitted = {}
    pending = deque()
    sequence = 0
    started = last_activity = time.monotonic()
    last_delivery = None
    delivered = 0
    delivery_error = ""
    while not stopping:
        current = scan(stage, patterns)
        if current != previous:
            last_activity = time.monotonic()
        for relative, identity in current.items():
            if previous.get(relative) != identity or emitted.get(relative) == identity:
                continue
            sequence += 1
            event = {
                "sequence": sequence, "status": "ready", "path": relative,
                "bytes": identity[2], "mtime_ns": identity[3],
                "device": identity[0], "inode": identity[1],
                "request_id": session,
            }
            with journal.open("a") as stream:
                stream.write(json.dumps(event, separators=(",", ":")) + "\n")
            pending.append(event)
            emitted[relative] = identity
        previous = current
        now = time.monotonic()
        if pending and now - last_activity >= options.update_timeout:
            batch = list(pending)
            if write_batch(events_fifo, batch):
                delivered += len(batch)
                pending.clear()
                last_delivery = time.monotonic()
        if not current and last_delivery is None and now - started >= options.initial_timeout:
            return 124
        if (last_delivery is not None and not pending
                and now - last_delivery >= result_timeout
                and now - last_activity >= options.update_timeout):
            break
        if pending and now - last_activity >= result_timeout:
            delivery_error = "events were not consumed before the session timeout"
            break
        time.sleep(SCAN_INTERVAL)
    print(json.dumps({
        "error_code": "1" if delivery_error else "0",
        "error_description": delivery_error,
        "path": str(stage), "events_delivered": delivered,
        "last_sequence": sequence,
    }, separators=(",", ":")))
    return 1 if delivery_error else 0


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
        if options.check_arguments:
            validate(arguments)
            print('{"error_code":"0","error_description":""}')
            return 0
        if options.prepare_api_channel:
            report = prepare(options.request_directory, arguments)
            (options.request_directory / "stage.json").write_text(json.dumps(report))
            print(json.dumps(report))
            return 0
        if not all((options.initial_timeout, options.update_timeout)):
            raise ValueError("processing requires positive timeouts")
        return run(options, arguments)
    except (OSError, ValueError) as error:
        print(json.dumps({"error_code": "1", "error_description": str(error)}))
        return 1


if __name__ == "__main__":
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    raise SystemExit(main())
