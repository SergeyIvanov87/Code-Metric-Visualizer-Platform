"""Bounded Linux FIFO transport for the existing, line-oriented API server."""

import errno
import fcntl
import os
from pathlib import Path
import stat
import threading
import time
from uuid import uuid4


class Unavailable(Exception):
    pass


class QueryTimeout(Exception):
    """The operation may have been accepted; callers must not retry it blindly."""


class InvalidResult(Exception):
    pass


def quote_value(value):
    # The CLI dispatcher uses `read -r` per line BEFORE its quote-aware parser.
    # CR preserves visual line breaks without inserting a second FIFO command.
    if "\0" in value:
        raise ValueError("NUL is not supported in filesystem API arguments")
    value = value.replace("\r\n", "\n").replace("\n", "\r")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class FifoClient:
    def __init__(self, api_mount, timeout_seconds=900, max_result_bytes=4194304):
        self.api_mount = Path(api_mount).resolve()
        self.timeout = timeout_seconds
        self.max_result_bytes = max_result_bytes
        self._sessions = threading.local()

    def node(self, schema):
        query = Path(schema["Query"])
        if query.is_absolute() or ".." in query.parts:
            raise ValueError("API Query must be a relative path without '..'")
        node = (self.api_mount / query / schema["Method"]).resolve()
        if not node.is_relative_to(self.api_mount):
            raise ValueError("API node escapes its mount")
        return node

    @staticmethod
    def _fifo(path):
        try:
            return stat.S_ISFIFO(path.lstat().st_mode)
        except FileNotFoundError:
            return False

    @staticmethod
    def _pause(deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise QueryTimeout("Filesystem API deadline exceeded; completion is unknown")
        time.sleep(min(0.01, remaining))

    def execute(self, schema, arguments):
        node = self.node(schema)
        exec_path = node / "exec"
        result_base = node / "result.json"
        if not self._fifo(exec_path) or not self._fifo(result_base):
            raise Unavailable("Filesystem API is not ready")
        # Reuse a completed session on each worker thread so the unmodified
        # agent does not accumulate a new result FIFO and Bash map entry for
        # every successful HTTP request. Abandon the ID after any uncertain I/O.
        session_id = getattr(self._sessions, "completed", None) or "http_" + uuid4().hex
        self._sessions.completed = None
        result_path = node / ("result.json_" + session_id)
        command = " ".join([f"SESSION_ID={session_id}", *(
            f"{key}={quote_value(value)}" for key, value in arguments.items()
        )]).encode("utf-8") + b"\n"
        deadline = time.monotonic() + self.timeout

        # Serialize writes between threads/processes/replicas sharing this mount.
        # Long prompt writes can exceed PIPE_BUF and otherwise interleave.
        locks = self.api_mount / ".http_embassador" / "locks"
        locks.mkdir(parents=True, exist_ok=True)
        lock_name = schema["Method"] + "_" + str(node.relative_to(self.api_mount)).replace("/", "_")
        with (locks / lock_name).open("a") as lock:
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    self._pause(deadline)
            fd = None
            try:
                while fd is None:
                    try:
                        fd = os.open(exec_path, os.O_WRONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
                        if not stat.S_ISFIFO(os.fstat(fd).st_mode):
                            raise Unavailable("exec is not a FIFO")
                    except OSError as exc:
                        if exc.errno not in (errno.ENXIO, errno.ENOENT):
                            raise
                        self._pause(deadline)
                offset = 0
                while offset < len(command):
                    self._pause(deadline)
                    try:
                        offset += os.write(fd, command[offset:])
                    except BlockingIOError:
                        continue
            finally:
                if fd is not None:
                    os.close(fd)
                fcntl.flock(lock, fcntl.LOCK_UN)

        while not self._fifo(result_path):
            self._pause(deadline)
        fd = os.open(result_path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        try:
            if not stat.S_ISFIFO(os.fstat(fd).st_mode):
                raise Unavailable("result is not a FIFO")
            chunks = []
            size = 0
            while True:
                self._pause(deadline)
                try:
                    chunk = os.read(fd, 65536)
                except BlockingIOError:
                    continue
                # Before the writer opens, a nonblocking FIFO also returns EOF.
                if not chunk:
                    if size:
                        self._sessions.completed = session_id
                        if size > self.max_result_bytes:
                            raise InvalidResult("Filesystem API result exceeds configured limit")
                        return b"".join(chunks)
                    continue
                size += len(chunk)
                # Drain an oversized result without retaining it, allowing the
                # agent's writer to finish. The same deadline still applies.
                if size <= self.max_result_bytes:
                    chunks.append(chunk)
        finally:
            os.close(fd)
            # Session FIFOs belong to the agent; never unlink or recreate them.
