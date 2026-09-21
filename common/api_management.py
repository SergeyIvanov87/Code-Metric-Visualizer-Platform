#!/usr/bin/python


import argparse
import os
import signal

SHUTDOWN_SIGNALS = {signal.SIGINT, signal.SIGTERM}
# A container can be stopped while this module or its local dependencies are
# still loading. Defer termination until the cleanup handler is ready.
signal.pthread_sigmask(signal.SIG_BLOCK, SHUTDOWN_SIGNALS)

import shutil
import sys

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
