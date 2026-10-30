#!/usr/bin/python


import argparse
import json
import os
import signal

SHUTDOWN_SIGNALS = {signal.SIGINT, signal.SIGTERM}
# A container can be stopped while this module or its local dependencies are
# still loading. Defer termination until the cleanup handler is ready.
signal.pthread_sigmask(signal.SIG_BLOCK, SHUTDOWN_SIGNALS)

import shutil
import sys
import time

from renew_pseudo_fs_pipes import remove_api_fs_pipes_node
from api_schema_utils import deserialize_api_request_from_schema_file


parser = argparse.ArgumentParser(
    prog="Gracefull shutdown supported at now"
)

parser.add_argument("api_schemas_location", help="An API json location directory")
parser.add_argument("domain_name_api_entry", help="build API queries processor for that particular domain")
parser.add_argument("mount_point", help="destination to build file-system nodes")
args = parser.parse_args()

schema_files = []
for api_schema_dir in args.api_schemas_location.split("|"):
    directory_str = os.fsdecode(api_schema_dir)
    schema_files.extend([os.path.join(directory_str, os.fsdecode(file)) for file in os.listdir(api_schema_dir) if os.fsdecode(file).endswith(".json")])

valid_queries_dict = {}
for schema_file in schema_files:
    req_name, request_data = deserialize_api_request_from_schema_file(schema_file)
    assert req_name
    assert request_data
    assert "Method" in request_data.keys()
    assert "Query" in request_data.keys()
    assert "Params" in request_data.keys()

    # filter out non-related queries
    domain_entry_pos = request_data["Query"].find(args.domain_name_api_entry)
    if domain_entry_pos == -1:
        continue
    valid_queries_dict[req_name] = request_data

shutdown_started = False


def signal_deferred_executors(mount_point):
    """Discover verified deferred request owners and ask them to terminate."""
    registrations = []
    for root, _directories, files in os.walk(mount_point):
        if "executor.json" not in files:
            continue
        registry = os.path.join(root, "executor.json")
        try:
            with open(registry, encoding="utf-8") as registry_file:
                registration = json.load(registry_file)
                pid = int(registration["pid"])
                session_lock = registration["session_lock"]
            with open(f"/proc/{pid}/cmdline", "rb") as command_file:
                command_line = command_file.read().replace(b"\0", b" ").decode()
            if "deferred_query_executor.py" not in command_line or root not in command_line:
                continue
            os.kill(pid, signal.SIGTERM)
            registrations.append((pid, root, session_lock))
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError,
                KeyError, json.JSONDecodeError):
            continue

    return registrations


def reap_deferred_executors(registrations, timeout=5.0):
    """Wait for signalled owners, escalate if needed, and remove artifacts."""
    deadline = time.monotonic() + timeout
    remaining = list(registrations)
    while remaining and time.monotonic() < deadline:
        alive = []
        for pid, directory, session_lock in remaining:
            try:
                os.kill(pid, 0)
                alive.append((pid, directory, session_lock))
            except ProcessLookupError:
                pass
        remaining = alive
        if remaining:
            time.sleep(0.05)
    for pid, _directory, _session_lock in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for _pid, directory, session_lock in registrations:
        shutil.rmtree(directory, ignore_errors=True)
        shutil.rmtree(session_lock, ignore_errors=True)
def unblock_pipes_signal_handler(sig, frame):
    global valid_queries_dict
    global args
    global shutdown_started

    if shutdown_started:
        return
    shutdown_started = True

    print(f'Signal caught: {sig}', flush=True)
    deleted_pipes = []
    cleanup_errors = []
    deferred_executors = signal_deferred_executors(args.mount_point)
    print(f"Signalled deferred executors: {deferred_executors}", flush=True)
    for communication_type in ("server", "client"):
        print(f"unblock {communication_type} pipes", flush=True)
        for req_name, query in valid_queries_dict.items():
            try:
                deleted_pipes.extend(
                    remove_api_fs_pipes_node(
                        args.mount_point,
                        communication_type,
                        query["Query"],
                        query["Method"],
                    )
                )
            except Exception as error:
                cleanup_errors.append((req_name, communication_type, error))
                print(
                    f"Failed to clean {communication_type} pipes for {req_name}: {error}",
                    file=sys.stderr,
                    flush=True,
                )

    reap_deferred_executors(deferred_executors)
    print(f"Reaped deferred executors: {deferred_executors}", flush=True)

    exec_node_directories = {os.path.dirname(path) for path in deleted_pipes}
    for d in exec_node_directories:
        try:
            shutil.rmtree(d)
        except FileNotFoundError:
            pass
        except OSError as error:
            cleanup_errors.append((d, "directory", error))
            print(f"Failed to remove API directory {d}: {error}", file=sys.stderr, flush=True)
    removed_paths = deleted_pipes + sorted(exec_node_directories)
    print(f"Removed API paths: {removed_paths}", flush=True)
    raise SystemExit(1 if cleanup_errors else 0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, unblock_pipes_signal_handler)
    signal.signal(signal.SIGTERM, unblock_pipes_signal_handler)
    signal.pthread_sigmask(signal.SIG_UNBLOCK, SHUTDOWN_SIGNALS)
    signal.pause()
