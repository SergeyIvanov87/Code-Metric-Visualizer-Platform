#!/usr/bin/python


import argparse
import os
import signal
import stat
import sys



from renew_pseudo_fs_pipes import remove_api_fs_pipes_node
from api_schema_utils import deserialize_api_request_from_schema_file
import subprocess
from subprocess import check_output


parser = argparse.ArgumentParser(
    prog="Gracefull shutdown supported at now"
)

parser.add_argument("api_schemas_location", help="An API json location directory")
parser.add_argument("domain_name_api_entry", help="build API queries processor for that particular domain")
parser.add_argument("mount_point", help="destination to build file-system nodes")
args = parser.parse_args()

directory_str = os.fsdecode(args.api_schemas_location)
schema_files =  [os.path.join(directory_str, os.fsdecode(file)) for file in os.listdir(args.api_schemas_location) if os.fsdecode(file).endswith(".json")]

valid_queries_dict = {}
for schema_file in schema_files:
    req_name, request_data = deserialize_api_request_from_schema_file(schema_file)
    assert req_name
    assert request_data
    assert "Method" in request_data.keys()
    assert "Query" in request_data.keys()
    assert "Params" in request_data.keys()
    valid_queries_dict[req_name] = request_data

    # filter out non-related queries
    domain_entry_pos = request_data["Query"].find(args.domain_name_api_entry)
    if domain_entry_pos == -1:
        continue

def unblock_pipes_signal_handler(sig, frame):
    global valid_queries_dict
    global args
    print(f'Signal catched: {sig}')
    deleted_pipes = []
    print(f"unblock server pipes")
    for req_name,query in valid_queries_dict.items():
        req_type = query["Method"]
        req_api = query["Query"]
        deleted_pipes.extend(remove_api_fs_pipes_node(args.mount_point, "server", req_api, req_type))

    print(f"unblock clien pipes")
    for req_name,query in valid_queries_dict.items():
        req_type = query["Method"]
        req_api = query["Query"]
        deleted_pipes.extend(remove_api_fs_pipes_node(args. mount_point, "client", req_api, req_type))

    print(f"{deleted_pipes}")
    sys.exit(0)

signal.signal(signal.SIGINT, unblock_pipes_signal_handler)
signal.signal(signal.SIGTERM, unblock_pipes_signal_handler)
signal.pause()

'''
def get_pids(name):
    return map(int,check_output(["pidof",name]).split())

def kill_server(pid, server_name):
    server_shutdown_script = 'bash -c "pkill -KILL -e -P ' + str(pid) + ' && kill -KILL ' + str(pid) + '"'
    print(f"execute shutdown script: {server_shutdown_script}")
    proc=subprocess.Popen(server_shutdown_script, shell=True)

    try:
        proc.wait(5)
    except Exception:
        print(f"Error killing: {server_name}. Skip it")
        proc.kill()
    else:
        print(f"Finished: {server_name}")

--> procedure (doesn't work, why?)
    for name,query in valid_queries_dict.items():
        print(f"Send signal to pids of {name}_listener.sh", file=sys.stdout, flush=True)
        pids = list(get_pids(f"{name}_listener.sh"))
        for p in pids:
            kill_server(p, f"{name}_listener.sh")

    for name,query in valid_queries_dict.items():
        print(f"Send signal to pids of {name}_server.sh", file=sys.stdout, flush=True)
        pids = list(get_pids(f"{name}_server.sh"))
        for p in pids:
            kill_server(p, f"{name}_server.sh")
'''
