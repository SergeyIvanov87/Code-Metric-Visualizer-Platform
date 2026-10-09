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
MAX_DIRECTORIES = 10000
MAX_TOTAL_BYTES = 100 * 1024 * 1024 * 1024
SCAN_INTERVAL = 0.05
DEFAULT_DIR_SKIP_REGEX = r"(?:^|.*/)(?:[.][^/]+|__pycache__|__pypackages__|node_modules)"
QUERY_PARAMETER_DEFAULTS = {
    "file_allow_regex": ".*",
    "file_skip_regex": r"(?!)",
    "dir_allow_regex": ".*",
    "dir_skip_regex": DEFAULT_DIR_SKIP_REGEX,
    "WaitInitialQueryTimeoutSec": "60",
    "WaitQueryUpdateTimeoutSec": "10",
    "WaitResultConsumptionTimeoutSec": "60",
    "SESSION_ID": "default",
}
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
    if len(arguments) % 2:
        raise ValueError("query arguments must be name/value pairs")
    names = {arguments[index].lstrip("-") for index in range(0, len(arguments), 2)}
    unknown = names - QUERY_PARAMETER_DEFAULTS.keys()
    if unknown:
        raise ValueError(f"unsupported query parameters: {', '.join(sorted(unknown))}")
    defaults = QUERY_PARAMETER_DEFAULTS
    patterns = (
        regex_value(arguments, "file_allow_regex", defaults["file_allow_regex"]),
        regex_value(arguments, "file_skip_regex", defaults["file_skip_regex"]),
        regex_value(arguments, "dir_allow_regex", defaults["dir_allow_regex"]),
        regex_value(arguments, "dir_skip_regex", defaults["dir_skip_regex"]),
    )
    session = value_of(arguments, "SESSION_ID", defaults["SESSION_ID"])
    if not re.fullmatch(r"[A-Za-z0-9_.:@+-]{1,128}", session):
        raise ValueError("SESSION_ID must contain 1-128 safe characters")
    return patterns, session


def staging_root(request):
    """Return the staging volume shared with consumers such as RAG bulk add."""
    configured = os.environ.get("STAGING_ROOT")
    root = Path(configured) if configured else request.parent / ".staging"
    created = not root.exists()
    root.mkdir(mode=0o2777, exist_ok=True)
    if created:
        # API clients and consumers can have different rootless UID mappings.
        root.chmod(0o2777)
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("shared staging root is not a directory")
    return root


def prepare(request, arguments):
    _, session = validate(arguments)
    request = request.resolve(strict=True)
    root = staging_root(request)
    stage = root / f"events-{session}-{request.name}"
    stage.mkdir(mode=0o2777)
    stage.chmod(0o2777)
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
    seal_fifo = request / "seal"
    os.mkfifo(seal_fifo, 0o620)
    return {
        "input": str(input_path), "input_type": "DIRECTORY",
        "staging": str(stage), "staging_type": "DIRECTORY",
        "events": str(events_fifo), "events_type": "FIFO",
        "seal": str(seal_fifo), "seal_type": "FIFO",
        "protocol": "cmvp.directory-events.v1",
    }


def safe_relative(stage, path):
    relative = path.relative_to(stage)
    text = PurePosixPath(*relative.parts).as_posix()
    if (not text or ".." in relative.parts or len(relative.parts) > MAX_DEPTH
            or len(os.fsencode(text)) > MAX_PATH_BYTES):
        raise ValueError(f"unsafe relative path: {text!r}")
    return text


def scan(stage, patterns, previously_observed):
    """Return accepted files, all observed names, and whether a name appeared."""
    file_allow, file_skip, dir_allow, dir_skip = patterns
    found = {}
    observed = set()
    admitted_directories = 0
    for root, directories, files in os.walk(stage, followlinks=False):
        root_path = Path(root)
        for name in directories[:]:
            node = root_path / name
            relative = safe_relative(stage, node)
            observed.add(relative)
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
            else:
                admitted_directories += 1
        for name in files:
            node = root_path / name
            relative = safe_relative(stage, node)
            observed.add(relative)
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
    if admitted_directories > MAX_DIRECTORIES:
        raise ValueError("shared staging directory admission limit exceeded")
    if len(found) > MAX_FILES or sum(item[2] for item in found.values()) > MAX_TOTAL_BYTES:
        raise ValueError("shared staging admission limit exceeded")
    return found, observed, bool(observed - previously_observed)


class EventWriter:
    """Keep a reader connection open and flush queued events as JSON Lines."""

    def __init__(self, path):
        self.path = path
        self.descriptor = None
        self.payload = None
        self.batch = []
        self.offset = 0

    def flush(self, pending):
        delivered = []
        try:
            if self.descriptor is None:
                self.descriptor = os.open(
                    self.path, os.O_WRONLY | os.O_NONBLOCK,
                )
            if self.payload is None and pending:
                self.batch = list(pending)
                self.payload = json.dumps({
                    "first_sequence": self.batch[0]["sequence"],
                    "last_sequence": self.batch[-1]["sequence"],
                    "events": self.batch,
                }, separators=(",", ":")).encode() + b"\n"
                self.offset = 0
            while self.payload is not None and self.offset < len(self.payload):
                self.offset += os.write(
                    self.descriptor, self.payload[self.offset:],
                )
            if self.payload is not None:
                for _ in self.batch:
                    pending.popleft()
                delivered = self.batch
                self.payload = None
                self.batch = []
                self.offset = 0
            return delivered
        except OSError as error:
            if error.errno not in (
                    errno.EPIPE, errno.ENXIO, errno.EAGAIN, errno.EWOULDBLOCK):
                raise
            if error.errno in (errno.EPIPE, errno.ENXIO):
                self.close(reset_payload=True)
            return []

    def close(self, reset_payload=False):
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None
        if reset_payload:
            self.payload = None
            self.batch = []
            self.offset = 0


def seal_requested(descriptor):
    try:
        return bool(os.read(descriptor, 4096))
    except BlockingIOError:
        return False


def run(options, arguments):
    patterns, session = validate(arguments)
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
    seal_fifo = request / "seal"
    if not seal_fifo.is_fifo():
        raise ValueError("prepared seal channel is not a FIFO")
    seal_descriptor = os.open(seal_fifo, os.O_RDONLY | os.O_NONBLOCK)
    writer = EventWriter(events_fifo)
    journal = request / "event_journal.jsonl"
    previous = {}
    previously_observed = set()
    emitted = {}
    pending = deque()
    sequence = 0
    started = last_activity = time.monotonic()
    activity_seen = False
    sealed = False
    post_seal_scan_required = False
    seal_reason = ""
    delivered = 0
    generated = 0
    termination_delivered = False
    try:
        while not stopping:
            current, observed, appeared = scan(
                stage, patterns, previously_observed,
            )
            now = time.monotonic()
            if appeared:
                last_activity = now
                activity_seen = True
            for relative, identity in current.items():
                if (previous.get(relative) != identity
                        or emitted.get(relative) == identity):
                    continue
                sequence += 1
                generated += 1
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

            for event in writer.flush(pending):
                if event["status"] == "ready":
                    delivered += 1

            if not sealed and seal_requested(seal_descriptor):
                sealed = True
                post_seal_scan_required = True
                seal_reason = "explicit"
            if (not sealed and activity_seen
                    and now - last_activity >= options.update_timeout):
                sealed = True
                post_seal_scan_required = True
                seal_reason = "idle timeout"
            if (not sealed and not activity_seen
                    and now - started >= options.initial_timeout):
                return 124

            all_stable_events_created = all(
                emitted.get(relative) == identity
                for relative, identity in current.items()
            )
            previous = current
            previously_observed = observed
            if sealed:
                if post_seal_scan_required:
                    # A producer can rename its final file after this scan but
                    # before the seal read. Always reconcile at least once more.
                    post_seal_scan_required = False
                elif all_stable_events_created:
                    break
            time.sleep(SCAN_INTERVAL)

        sequence += 1
        terminal = {
            "sequence": sequence,
            "status": "terminated",
            "reason": seal_reason or "processor stopped",
            "request_id": session,
            "events_generated": generated,
            "events_delivered": delivered,
            "events_undelivered": generated - delivered,
        }
        with journal.open("a") as stream:
            stream.write(json.dumps(terminal, separators=(",", ":")) + "\n")
        pending.append(terminal)
        deadline = time.monotonic() + 1
        while pending and not stopping and time.monotonic() < deadline:
            sent = writer.flush(pending)
            for event in sent:
                if event["status"] == "ready":
                    delivered += 1
                elif event["status"] == "terminated":
                    termination_delivered = True
            if pending:
                time.sleep(0.02)
    finally:
        writer.close()
        os.close(seal_descriptor)

    print(json.dumps({
        "error_code": "0", "error_description": "",
        "path": str(stage), "seal_reason": seal_reason,
        "events_generated": generated, "events_delivered": delivered,
        "events_undelivered": generated - delivered,
        "termination_event_delivered": termination_delivered,
        "last_sequence": sequence,
    }, separators=(",", ":")))
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
