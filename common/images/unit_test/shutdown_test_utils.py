"""Reusable shutdown operations with explicit inputs and no retained test state.

Tests own clients, events, callbacks and assertions about execution mode. These
helpers only perform the requested filesystem/process operation; they do not
capture settings, track clients or change caller-owned collections.
"""

import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time


def queries_for_execution_mode(queries, parallel_by_session):
    """Return a new parameter list without changing the input schemas."""
    return [
        (name, query) for name, query in queries
        if query.get("ParallelBySession", False) is parallel_by_session
    ]


def wait_for_fifos(paths, timeout=3, interval=0.1):
    """Wait for all supplied paths to be FIFOs within one deadline."""
    deadline = time.monotonic() + timeout
    while True:
        missing = []
        for path in paths:
            try:
                ready = stat.S_ISFIFO(os.stat(path).st_mode)
            except FileNotFoundError:
                ready = False
            if not ready:
                missing.append(path)
        if not missing:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"FIFOs did not become ready: {missing}")
        time.sleep(min(interval, remaining))


def install_blocking_command(command_path):
    """Install an executor that remains blocked until the test kills it."""
    path = Path(command_path)
    path.write_text("#!/usr/bin/env bash\nsleep infinity &\nwait $!\necho 'finishing'\n")
    path.chmod(0o755)


def kill_process_groups(pids):
    """Kill the supplied server processes and reap direct children."""
    for pid in pids:
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except ProcessLookupError:
            # Another PID in the same group may already have killed it.
            pass
    for pid in pids:
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            # Descendants are reaped by their parent, not by the test process.
            pass


def pipe_cleanup_command(api_dir, query_path, method):
    """Purely construct the cleanup invocation, passing paths as arguments."""
    return [
        sys.executable, "-c",
        "import sys\n"
        "from renew_pseudo_fs_pipes import remove_api_fs_pipes_node\n"
        "for side in ('server', 'client'):\n"
        "    removed = remove_api_fs_pipes_node(sys.argv[1], side, sys.argv[2], sys.argv[3])\n"
        "    if not removed:\n"
        "        raise SystemExit(f'No {side} API nodes removed')\n",
        str(api_dir), query_path, method,
    ]


def cleanup_api_pipes(api_dir, query_path, method, timeout=20):
    """Fork-based pipe cleanup must run outside the threaded test process."""
    subprocess.run(
        pipe_cleanup_command(api_dir, query_path, method),
        check=True, capture_output=True, text=True, timeout=timeout,
    )


def assert_api_pipes_removed(paths):
    for path in paths:
        assert not os.path.exists(path), f"API pipe remains: {path}"
    for directory in {Path(path).parent for path in paths}:
        assert not list(directory.glob("result*")), f"Session result pipes remain in {directory}"
