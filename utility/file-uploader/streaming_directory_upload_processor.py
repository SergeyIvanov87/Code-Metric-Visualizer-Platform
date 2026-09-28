#!/usr/bin/env python3
"""Ingest a directory through bounded clients of streaming_file_upload."""

import argparse
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path, PurePosixPath
import queue
import re
import shutil
import signal
import stat
import threading
import time

CHUNK_SIZE = 64 * 1024
MAX_WORKERS = 32
MAX_PATH_BYTES = 1024
MAX_DEPTH = 64
MAX_FILES = 10000
MAX_DIRECTORIES = 10000
MAX_TOTAL_BYTES = 100 * 1024 * 1024 * 1024
RECONCILE_INTERVAL = 0.1
stop_event = threading.Event()
# The generated pseudo-filesystem API uses one shared exec FIFO. A request is
# framed by its writer closing that FIFO, so two writers must never overlap:
# otherwise the server reads both argument strings as one request. Keep the
# lock until the server has published and we have consumed the handshake;
# publication proves it observed EOF for this request.
nested_allocation_lock = threading.Lock()


def value_of(arguments, name, default=None):
    for index in range(0, len(arguments) - 1, 2):
        if arguments[index].lstrip("-") == name:
            return arguments[index + 1]
    if default is not None:
        return default
    raise ValueError(f"missing {name}")


def normalize_empty(value):
    return "" if value in ("", '""', "''") else value


def validate_request_dir(path):
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"request directory is not a directory: {path}")
    return resolved


def validate_arguments(arguments):
    metadata_text = normalize_empty(value_of(arguments, "metadata", "{}"))
    metadata = json.loads(metadata_text or "{}")
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a JSON object")
    destination = Path(value_of(arguments, "destination", "/uploads")).resolve(strict=True)
    if not destination.is_dir() or not os.access(destination, os.W_OK):
        raise ValueError("destination must be an existing writable directory")
    preferred = normalize_empty(value_of(arguments, "preferred_directory", ""))
    if preferred and (Path(preferred).name != preferred or preferred in (".", "..")):
        raise ValueError("preferred_directory must be a base name")
    try:
        workers = int(value_of(arguments, "workers", "4"))
    except ValueError:
        raise ValueError("workers must be an integer") from None
    if not 1 <= workers <= MAX_WORKERS:
        raise ValueError(f"workers must be between 1 and {MAX_WORKERS}")
    pattern_text = value_of(arguments, "file_regex", ".*")
    if len(pattern_text) > 1024:
        raise ValueError("file_regex exceeds 1024 characters")
    try:
        pattern = re.compile(pattern_text)
    except re.error as error:
        raise ValueError(f"invalid file_regex: {error}") from None
    if value_of(arguments, "conflict_policy", "fail") != "fail":
        raise ValueError("conflict_policy must be 'fail'")
    try:
        heartbeat = float(value_of(arguments, "StatusHeartbeatIntervalSec", "1"))
    except ValueError:
        raise ValueError("StatusHeartbeatIntervalSec must be a number") from None
    if not 0.05 <= heartbeat <= 3600:
        raise ValueError("StatusHeartbeatIntervalSec must be between 0.05 and 3600")
    session = value_of(arguments, "SESSION_ID", "default")
    if len(session) > 118:
        raise ValueError("SESSION_ID must be at most 118 characters for directory upload")
    final = destination / preferred if preferred else None
    if final is not None and final.exists():
        raise FileExistsError(f"preferred directory already exists: {final}")
    return metadata, destination, preferred, workers, pattern, heartbeat, session


def staging_root():
    return Path(os.environ.get("FILE_UPLOADER_STAGING_ROOT", "/dev/shm/file-uploader"))


def prepare_channels(request_directory, arguments):
    request = validate_request_dir(request_directory)
    _, _, _, workers, _, _, _ = validate_arguments(arguments)
    root = staging_root()
    root.mkdir(mode=0o2770, parents=True, exist_ok=True)
    root = root.resolve(strict=True)
    stage = root / request.name
    stage.mkdir(mode=0o2770)
    input_link = request / "input"
    input_link.symlink_to(stage, target_is_directory=True)
    statuses = []
    try:
        if input_link.resolve(strict=True) != stage or not stage.is_relative_to(root):
            raise ValueError("staging directory escaped staging root")
        for worker_id in range(1, workers + 1):
            status_path = request / f"status-{worker_id}"
            os.mkfifo(status_path, 0o660)
            if not stat.S_ISFIFO(status_path.lstat().st_mode):
                raise ValueError(f"status channel is not a FIFO: {status_path}")
            statuses.append(str(status_path))
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return {
        "input": str(input_link), "input_type": "DIRECTORY",
        "status": statuses, "status_type": "FIFO[]",
        "protocol": "cmvp.directory-upload.v1",
    }


def generated_directory(destination):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%f")[:-3] + "Z"
    base = f"uploaded.{stamp}"
    candidate = base
    suffix = 0
    while (destination / candidate).exists():
        suffix += 1
        candidate = f"{base}.{suffix}"
    return candidate


class StatusWriter:
    def __init__(self, path, worker_id):
        self.path, self.worker_id = path, worker_id
        self.descriptor = None

    def emit(self, relative, copied, total, status_value):
        record = json.dumps({
            "worker_id": self.worker_id, "path": relative,
            "bytes": copied, "total_bytes": total, "status": status_value,
        }, separators=(",", ":")).encode() + b"\n"
        pipe_buf = os.pathconf(self.path, "PC_PIPE_BUF")
        if len(record) > pipe_buf:
            return
        try:
            if self.descriptor is None:
                self.descriptor = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
            os.write(self.descriptor, record)
        except OSError as error:
            if error.errno in (errno.EPIPE, errno.ENXIO):
                self.close()
            elif error.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                raise

    def close(self):
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None


def wait_for_path(path, timeout, fifo=False):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not stop_event.is_set():
        try:
            mode = path.stat().st_mode
            if not fifo or stat.S_ISFIFO(mode):
                return path
        except FileNotFoundError:
            pass
        time.sleep(0.02)
    raise TimeoutError(f"timed out waiting for {path}")


def wait_for_absence(path, timeout):
    """Wait for a prior session artifact to be removed before session reuse."""
    deadline = time.monotonic() + timeout
    while path.exists() and time.monotonic() < deadline and not stop_event.is_set():
        time.sleep(0.02)
    if path.exists():
        raise TimeoutError(f"timed out waiting for stale API artifact cleanup: {path}")


def allocate_nested_upload(api_directory, result_fifo, request):
    """Atomically frame one request on the shared exec FIFO and read its reply."""
    with nested_allocation_lock:
        # A worker reuses its derived session. Do not mistake the preceding
        # request's handshake FIFO for the response to this request.
        wait_for_absence(result_fifo, 5)
        exec_fifo = wait_for_path(api_directory / "exec", 5, fifo=True)
        exec_fifo.write_text(request)
        return json.loads(wait_for_path(result_fifo, 5, fifo=True).read_text())


def nested_upload(api_directory, session, worker_id, source, relative, destination,
                  metadata, writer, heartbeat, initial_timeout, update_timeout):
    nested_session = f"{session}.worker-{worker_id}"
    result_fifo = api_directory / f"result.json_{nested_session}"
    request = " ".join([
        f"SESSION_ID={nested_session}",
        f"metadata={json.dumps(metadata, separators=(',', ':'))}",
        f"preferred_filename={json.dumps(source.name)}",
        f"destination={json.dumps(str(destination))}",
        f"expected_bytes={source.stat().st_size}",
        f"WaitInitialQueryTimeoutSec={initial_timeout}",
        f"WaitQueryUpdateTimeoutSec={update_timeout}",
        "WaitResultConsumptionTimeoutSec=60",
    ])
    # The API parser uses shell request syntax; JSON strings safely preserve spaces.
    report = allocate_nested_upload(api_directory, result_fifo, request)
    api_root = api_directory.resolve(strict=True)
    input_fifo = Path(report["input"])
    output_fifo = Path(report["result"])
    for channel in (input_fifo, output_fifo):
        if not channel.resolve(strict=True).is_relative_to(api_root) or not channel.is_fifo():
            raise ValueError(f"nested API returned an unsafe channel: {channel}")

    source_stat = source.stat(follow_symlinks=False)
    if not stat.S_ISREG(source_stat.st_mode) or source_stat.st_nlink != 1:
        raise ValueError("source must be an unlinked regular file")
    sent = 0
    last_status = 0.0
    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        with os.fdopen(source_fd, "rb", closefd=True) as stream, input_fifo.open("wb", buffering=0) as output:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino, opened.st_size) != (
                    source_stat.st_dev, source_stat.st_ino, source_stat.st_size):
                raise ValueError("source identity changed before upload")
            while True:
                if stop_event.is_set():
                    raise InterruptedError("directory upload interrupted")
                chunk = stream.read(CHUNK_SIZE)
                if not chunk:
                    break
                output.write(chunk)
                sent += len(chunk)
                now = time.monotonic()
                if now - last_status >= heartbeat:
                    writer.emit(relative, sent, source_stat.st_size, "in progress")
                    last_status = now
        result = json.loads(wait_for_path(output_fifo, 65, fifo=True).read_text())
        if result.get("error_code") != "0" or result.get("received_bytes") != sent or sent != source_stat.st_size:
            raise RuntimeError(result.get("error_description") or "nested upload byte count mismatch")
        source.unlink()
        writer.emit(relative, sent, source_stat.st_size, "done")
        return sent
    except BaseException:
        writer.emit(relative, sent, source_stat.st_size, "failed")
        raise


def safe_relative(stage, path):
    relative = path.relative_to(stage)
    text = PurePosixPath(*relative.parts).as_posix()
    if (not text or text.startswith("/") or ".." in relative.parts or "\0" in text or
            len(os.fsencode(text)) > MAX_PATH_BYTES or len(relative.parts) > MAX_DEPTH):
        raise ValueError(f"unsafe relative path: {text!r}")
    return text


def process_directory(options, arguments):
    metadata, destination, preferred, workers, pattern, heartbeat, session = validate_arguments(arguments)
    request = validate_request_dir(options.request_directory)
    stage = (request / "input").resolve(strict=True)
    if not stage.is_relative_to(staging_root().resolve(strict=True)):
        raise ValueError("input directory is outside the staging root")
    final = destination / (preferred or generated_directory(destination))
    final.mkdir(mode=0o770)
    streaming_api = request.parent.parent.parent / "streaming_file_upload" / "POST"
    if not streaming_api.is_dir():
        override = os.environ.get("STREAMING_FILE_UPLOAD_API")
        if not override:
            raise ValueError(f"streaming_file_upload API not found: {streaming_api}")
        streaming_api = Path(override)

    tasks = queue.Queue(maxsize=max(32, workers * 4))
    lock = threading.Lock()
    result = {"completed": 0, "bytes": 0, "failed": [], "skipped": 0}
    queued = set()
    active = 0

    def worker(worker_id):
        nonlocal active
        status_writer = StatusWriter(request / f"status-{worker_id}", worker_id)
        try:
            while True:
                item = tasks.get()
                if item is None:
                    tasks.task_done()
                    return
                source, relative = item
                with lock:
                    active += 1
                try:
                    target_parent = final.joinpath(*PurePosixPath(relative).parts[:-1])
                    target_parent.mkdir(parents=True, exist_ok=True)
                    copied = nested_upload(
                        streaming_api, session, worker_id, source, relative, target_parent,
                        metadata, status_writer, heartbeat, options.initial_timeout,
                        options.update_timeout,
                    )
                    with lock:
                        result["completed"] += 1
                        result["bytes"] += copied
                except BaseException:
                    with lock:
                        result["failed"].append(relative)
                    stop_event.set()
                finally:
                    with lock:
                        active -= 1
                    tasks.task_done()
        finally:
            status_writer.close()

    threads = [threading.Thread(target=worker, args=(number,), daemon=True)
               for number in range(1, workers + 1)]
    for thread in threads:
        thread.start()

    started = time.monotonic()
    last_activity = None
    snapshots = {}
    directory_names = set()
    previous_directories = set()
    try:
        while not stop_event.is_set():
            current = {}
            current_directories = set()
            for root, directories, files in os.walk(stage, followlinks=False):
                root_path = Path(root)
                for name in directories:
                    node = root_path / name
                    relative = safe_relative(stage, node)
                    info = node.lstat()
                    if not stat.S_ISDIR(info.st_mode):
                        raise ValueError(f"unsupported directory entry: {relative}")
                    directory_names.add(relative)
                    current_directories.add(relative)
                for name in files:
                    node = root_path / name
                    relative = safe_relative(stage, node)
                    info = node.lstat()
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise ValueError(f"unsupported file entry: {relative}")
                    current[relative] = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
            if len(current) + len(queued) > MAX_FILES or len(directory_names) > MAX_DIRECTORIES:
                raise ValueError("directory ingestion admission limit exceeded")
            if sum(value[2] for value in current.values()) > MAX_TOTAL_BYTES:
                raise ValueError("directory ingestion byte limit exceeded")
            if current or current_directories != previous_directories:
                last_activity = time.monotonic()
            for relative, identity in current.items():
                if relative in queued or snapshots.get(relative) != identity:
                    continue
                source = stage.joinpath(*PurePosixPath(relative).parts)
                queued.add(relative)
                if pattern.fullmatch(relative):
                    tasks.put((source, relative))
                else:
                    source.unlink()
                    result["skipped"] += 1
            snapshots = current
            previous_directories = current_directories
            now = time.monotonic()
            with lock:
                idle = tasks.unfinished_tasks == 0 and active == 0
            remaining_files = any(path.is_file() for path in stage.rglob("*"))
            if last_activity is None:
                if now - started >= options.initial_timeout:
                    raise TimeoutError("no directory upload activity before initial timeout")
            elif idle and not remaining_files and now - last_activity >= options.update_timeout:
                break
            time.sleep(RECONCILE_INTERVAL)
        tasks.join()
    finally:
        for _ in threads:
            tasks.put(None)
        for thread in threads:
            thread.join(timeout=2)

    for directory in sorted(final.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if directory.is_dir():
            try:
                directory.rmdir()
            except OSError:
                pass
    accepted = result["completed"] + len(result["failed"])
    response = {
        "error_code": "0" if not result["failed"] else "1",
        "error_description": "" if not result["failed"] else "one or more files failed",
        "metadata": metadata, "path": str(final),
        "files_completed": f'{result["completed"]}/{accepted}',
        "directories_completed": f"{len(directory_names)}/{len(directory_names)}",
        "bytes_completed": result["bytes"],
        "files_failed": f'{len(result["failed"])}/{accepted}',
        "files_failed_path": sorted(result["failed"]), "files_skipped": result["skipped"],
    }
    print(json.dumps(response, separators=(",", ":")))


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
    processing = not options.check_arguments and not options.prepare_api_channel
    try:
        validate_request_dir(options.request_directory)
        if options.check_arguments:
            validate_arguments(arguments)
            print(json.dumps({"error_code": "0", "error_description": ""}))
        elif options.prepare_api_channel:
            print(json.dumps(prepare_channels(options.request_directory, arguments)))
        else:
            if not options.initial_timeout or not options.update_timeout:
                raise ValueError("processing requires positive upload timeouts")
            process_directory(options, arguments)
        return 0
    except TimeoutError:
        return 124
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(json.dumps({"error_code": str(getattr(error, "errno", None) or 1),
                          "error_description": str(error)}))
        return 1
    finally:
        if processing:
            try:
                link = options.request_directory / "input"
                target = link.resolve(strict=True)
                if target.is_relative_to(staging_root().resolve(strict=True)):
                    shutil.rmtree(target, ignore_errors=True)
            except (OSError, ValueError):
                pass


if __name__ == "__main__":
    for handled in (signal.SIGINT, signal.SIGTERM):
        signal.signal(handled, lambda *_: stop_event.set())
    raise SystemExit(main())
