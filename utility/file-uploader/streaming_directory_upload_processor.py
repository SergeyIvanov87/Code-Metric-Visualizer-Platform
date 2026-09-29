#!/usr/bin/env python3
"""Ingest a directory through bounded clients of streaming_file_upload."""

import argparse
from collections import deque
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
MATCH_NOTHING_REGEX = r"(?!)"
DEFAULT_DIR_SKIP_REGEX = (
    r"(?:^|.*/)(?:[.][^/]+|__pycache__|__pypackages__|node_modules)"
)
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


def boolean_value(arguments, name, default="false"):
    value = normalize_empty(value_of(arguments, name, default)).lower()
    if value not in ("true", "false"):
        raise ValueError(f"{name} must be true or false")
    return value == "true"


def has_argument(arguments, name):
    return any(
        arguments[index].lstrip("-") == name
        for index in range(0, len(arguments) - 1, 2)
    )


def regex_value(arguments, name, default):
    text = value_of(arguments, name, default)
    if len(text) > 1024:
        raise ValueError(f"{name} exceeds 1024 characters")
    try:
        return re.compile(text)
    except re.error as error:
        raise ValueError(f"invalid {name}: {error}") from None


def path_is_allowed(relative, allow_pattern, skip_pattern):
    return (
        allow_pattern.fullmatch(relative) is not None
        and skip_pattern.fullmatch(relative) is None
    )


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
    if has_argument(arguments, "file_regex"):
        raise ValueError("file_regex was renamed to file_allow_regex")
    file_allow_pattern = regex_value(arguments, "file_allow_regex", ".*")
    file_skip_pattern = regex_value(
        arguments, "file_skip_regex", MATCH_NOTHING_REGEX,
    )
    dir_allow_pattern = regex_value(arguments, "dir_allow_regex", ".*")
    dir_skip_pattern = regex_value(
        arguments, "dir_skip_regex", DEFAULT_DIR_SKIP_REGEX,
    )
    if value_of(arguments, "conflict_policy", "fail") != "fail":
        raise ValueError("conflict_policy must be 'fail'")
    tolerate_errors = boolean_value(arguments, "tolerate_errors")
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
    return (
        metadata, destination, preferred, workers,
        file_allow_pattern, file_skip_pattern,
        dir_allow_pattern, dir_skip_pattern,
        heartbeat, session, tolerate_errors,
    )


def prepare_channels(request_directory, arguments):
    request = validate_request_dir(request_directory)
    workers = validate_arguments(arguments)[3]
    # The API tree is the transport shared with both container and host
    # clients. Keep the staging directory in the request itself: an absolute
    # symlink into the container's /dev/shm is dangling from the host and makes
    # ordinary `cp -r source input/` fail.
    input_path = request / "input"
    input_path.mkdir(mode=0o2770)
    statuses = []
    try:
        if input_path.resolve(strict=True).parent != request:
            raise ValueError("input directory escaped request directory")
        for worker_id in range(1, workers + 1):
            status_path = request / f"status-{worker_id}"
            os.mkfifo(status_path, 0o660)
            if not stat.S_ISFIFO(status_path.lstat().st_mode):
                raise ValueError(f"status channel is not a FIFO: {status_path}")
            statuses.append(str(status_path))
    except BaseException:
        shutil.rmtree(input_path, ignore_errors=True)
        raise
    return {
        "input": str(input_path), "input_type": "DIRECTORY",
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
        self.pending = deque()

    def flush_pending(self):
        """Connect a waiting reader and deliver every queued record in order."""
        try:
            if self.descriptor is None:
                # O_WRONLY intentionally reports ENXIO when no reader is
                # attached. Unlike O_RDWR, it does not hide reader absence or
                # pretend queued records were delivered.
                self.descriptor = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
            while self.pending:
                os.write(self.descriptor, self.pending[0])
                self.pending.popleft()
            return True
        except OSError as error:
            if error.errno in (errno.EPIPE, errno.ENXIO):
                self.close()
            elif error.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                raise
            return False

    def emit(self, relative, copied, total, status_value, terminal=False):
        record = json.dumps({
            "worker_id": self.worker_id, "path": relative,
            "bytes": copied, "total_bytes": total, "status": status_value,
        }, separators=(",", ":")).encode() + b"\n"
        pipe_buf = os.pathconf(self.path, "PC_PIPE_BUF")
        if len(record) > pipe_buf:
            raise ValueError("status record exceeds the atomic FIFO write limit")
        # Preserve the complete ordered history while the reader is absent or
        # the FIFO is backpressured. A successful atomic write removes exactly
        # one record from this backlog.
        self.pending.append(record)
        # The backlog makes a special terminal-event wait unnecessary. Delivery
        # is retried by this worker before its next event and while it is idle.
        self.flush_pending()

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


def allocate_nested_upload(api_directory, result_fifo, request):
    """Atomically frame one request on the shared exec FIFO and read its reply."""
    with nested_allocation_lock:
        # Session result FIFOs are persistent API nodes. Writing the request
        # first ensures the subsequent read belongs to this allocation; the
        # server also waits for its previous response writer before accepting
        # another request for the same derived session.
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
                if sent < source_stat.st_size and now - last_status >= heartbeat:
                    writer.emit(relative, sent, source_stat.st_size, "in progress")
                    last_status = now
        result = json.loads(wait_for_path(output_fifo, 65, fifo=True).read_text())
        if result.get("error_code") != "0" or result.get("received_bytes") != sent or sent != source_stat.st_size:
            raise RuntimeError(result.get("error_description") or "nested upload byte count mismatch")
        # The staging copy is consumed only after the destination confirms the
        # exact byte count. A failed unlink therefore turns the file into a
        # reported worker failure instead of claiming completion.
        source.unlink()
        writer.emit(relative, sent, source_stat.st_size, "done", terminal=True)
        return sent
    except BaseException:
        writer.emit(relative, sent, source_stat.st_size, "failed", terminal=True)
        raise


def safe_relative(stage, path):
    relative = path.relative_to(stage)
    text = PurePosixPath(*relative.parts).as_posix()
    if (not text or text.startswith("/") or ".." in relative.parts or "\0" in text or
            len(os.fsencode(text)) > MAX_PATH_BYTES or len(relative.parts) > MAX_DEPTH):
        raise ValueError(f"unsafe relative path: {text!r}")
    return text


def skip_unsupported_entry(path):
    """Remove an unsupported staging node without following it."""
    try:
        path.unlink()
    except OSError:
        # The request cleanup removes any node the producer made immutable or
        # raced with us. Unsupported entries never become upload tasks.
        pass


def lstat_if_exists(path):
    """Return lstat data, or None when a concurrently consumed node vanished."""
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def record_worker_failure(result, lock, relative, failed, tolerate_errors):
    with lock:
        result["failed"].append(relative)
    if not tolerate_errors:
        failed.set()


def build_response(metadata, final, result, directory_names, error=None):
    accepted = result["completed"] + len(result["failed"])
    if error is not None:
        error_code = str(getattr(error, "errno", None) or 1)
        error_description = str(error)
    elif result["failed"]:
        error_code = "1"
        error_description = "one or more files failed"
    else:
        error_code = "0"
        error_description = ""
    return {
        "error_code": error_code, "error_description": error_description,
        "metadata": metadata, "path": str(final),
        "files_completed": "{}/{}".format(result["completed"], accepted),
        "directories_completed": "{}/{}".format(
            len(directory_names), len(directory_names),
        ),
        "bytes_completed": result["bytes"],
        "files_failed": "{}/{}".format(len(result["failed"]), accepted),
        "files_failed_path": sorted(result["failed"]),
        "files_skipped": result["skipped"],
        "items_skipped": len(result["unsupported"]),
        "items_skipped_path": sorted(result["unsupported"]),
    }


def process_directory(options, arguments):
    (metadata, destination, preferred, workers,
     file_allow_pattern, file_skip_pattern,
     dir_allow_pattern, dir_skip_pattern,
     heartbeat, session, tolerate_errors) = validate_arguments(arguments)
    request = validate_request_dir(options.request_directory)
    stage = (request / "input").resolve(strict=True)
    if stage.parent != request:
        raise ValueError("input directory is outside the request directory")
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
    result = {
        "completed": 0, "bytes": 0, "failed": [], "skipped": 0,
        "unsupported": set(),
    }
    queued = set()
    accepted_file_names = set()
    active = 0
    failed = threading.Event()

    def worker(worker_id):
        nonlocal active
        status_writer = StatusWriter(request / f"status-{worker_id}", worker_id)
        try:
            while True:
                try:
                    item = tasks.get(timeout=0.1)
                except queue.Empty:
                    # Retry queued statuses for late readers and connect an idle
                    # worker's waiting reader so it receives EOF later.
                    status_writer.flush_pending()
                    continue
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
                    # A business failure never cancels workers already in
                    # flight. tolerate_errors additionally keeps discovery and
                    # scheduling open for later files.
                    record_worker_failure(
                        result, lock, relative, failed, tolerate_errors,
                    )
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
    unsupported_inodes = set()
    processing_error = None
    try:
        while not stop_event.is_set() and not failed.is_set():
            current = {}
            current_directories = set()
            excluded_directories = set()
            observed_activity = False
            for root, directories, files in os.walk(stage, followlinks=False):
                root_path = Path(root)
                root_relative = (
                    "" if root_path == stage else safe_relative(stage, root_path)
                )
                root_is_excluded = root_relative in excluded_directories
                for name in directories[:]:
                    node = root_path / name
                    relative = safe_relative(stage, node)
                    info = lstat_if_exists(node)
                    if info is None:
                        # A worker may have consumed the node after os.walk
                        # captured the directory listing.
                        directories.remove(name)
                        continue
                    if not stat.S_ISDIR(info.st_mode):
                        # Prevent os.walk from considering this node for
                        # descent, then remove it without following links.
                        directories.remove(name)
                        skip_unsupported_entry(node)
                        if (not root_is_excluded and
                                relative not in result["unsupported"]):
                            result["unsupported"].add(relative)
                            observed_activity = True
                        continue
                    current_directories.add(relative)
                    if (
                        root_is_excluded
                        or not path_is_allowed(
                            relative, dir_allow_pattern, dir_skip_pattern,
                        )
                    ):
                        excluded_directories.add(relative)
                    else:
                        directory_names.add(relative)
                for name in files:
                    node = root_path / name
                    relative = safe_relative(stage, node)
                    info = lstat_if_exists(node)
                    if info is None:
                        # Normal TOCTOU race: successful workers unlink their
                        # source files while reconciliation is walking.
                        continue
                    inode = (info.st_dev, info.st_ino)
                    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                            inode in unsupported_inodes):
                        if stat.S_ISREG(info.st_mode):
                            unsupported_inodes.add(inode)
                        skip_unsupported_entry(node)
                        if (not root_is_excluded and
                                relative not in result["unsupported"]):
                            result["unsupported"].add(relative)
                            observed_activity = True
                        continue
                    file_is_allowed = (
                        info.st_size > 0
                        and not root_is_excluded
                        and path_is_allowed(
                            relative, file_allow_pattern, file_skip_pattern,
                        )
                    )
                    current[relative] = (
                        info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                        file_is_allowed,
                    )
            admitted_file_names = accepted_file_names.union(
                relative
                for relative, identity in current.items()
                if identity[4]
            )
            if (len(admitted_file_names) > MAX_FILES or
                    len(directory_names) > MAX_DIRECTORIES):
                raise ValueError(
                    "items ingestion admission limit exceeded, limits are: "
                    f"directories [{len(directory_names)}/{MAX_DIRECTORIES}], "
                    f"files [{len(admitted_file_names)}/{MAX_FILES}]"
                )
            byte_sum = sum(
                identity[2] for identity in current.values() if identity[4]
            )
            if byte_sum > MAX_TOTAL_BYTES:
                raise ValueError(
                    "directory ingestion byte limit exceeded: "
                    f"[{byte_sum}/{MAX_TOTAL_BYTES}]"
                )
            files_changed = any(
                snapshots.get(relative) != identity
                for relative, identity in current.items()
            )
            if files_changed or observed_activity or current_directories != previous_directories:
                last_activity = time.monotonic()
            for relative, identity in current.items():
                if failed.is_set():
                    break
                if relative in queued or snapshots.get(relative) != identity:
                    continue
                source = stage.joinpath(*PurePosixPath(relative).parts)
                queued.add(relative)
                if identity[4]:
                    accepted_file_names.add(relative)
                    tasks.put((source, relative))
                else:
                    source.unlink()
                    result["skipped"] += 1
            snapshots = current
            previous_directories = current_directories
            now = time.monotonic()
            with lock:
                idle = tasks.unfinished_tasks == 0 and active == 0
            # Failed sources deliberately remain for request cleanup. They have
            # already reached a terminal state and must not prevent tolerant
            # requests from completing their quiet period.
            remaining_files = any(relative not in queued for relative in current)
            if last_activity is None:
                if now - started >= options.initial_timeout:
                    raise TimeoutError("no directory upload activity before initial timeout")
            elif idle and not remaining_files and now - last_activity >= options.update_timeout:
                break
            time.sleep(RECONCILE_INTERVAL)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        processing_error = error
    finally:
        # Finish every task accepted before discovery failed so the aggregate
        # response reflects all transfers that reached a worker.
        tasks.join()
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
    response = build_response(
        metadata, final, result, directory_names, processing_error,
    )
    print(json.dumps(response, separators=(",", ":")))
    return 0 if response["error_code"] == "0" else 1


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
            return process_directory(options, arguments)
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
                request = validate_request_dir(options.request_directory)
                input_path = (request / "input").resolve(strict=True)
                if input_path.parent == request:
                    shutil.rmtree(input_path, ignore_errors=True)
            except (OSError, ValueError):
                pass


if __name__ == "__main__":
    for handled in (signal.SIGINT, signal.SIGTERM):
        signal.signal(handled, lambda *_: stop_event.set())
    raise SystemExit(main())
