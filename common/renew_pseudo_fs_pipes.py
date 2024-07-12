#!/usr/bin/python


import argparse
import errno
import os
import subprocess
import stat
import sys

sys.path.append('modules')

import filesystem_utils

from api_fs_conventions import compose_api_fs_request_location_paths
from api_fs_conventions import api_gui_exec_filename_from_req_type
from api_fs_conventions import get_api_schema_files

from api_schema_utils import deserialize_api_request_from_schema_file

def remove_file(filename):
    try:
        os.remove(filename)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise

def remove_pipe(filename):
    if (os.path.exists(filename) and stat.S_ISFIFO(os.stat(filename).st_mode)):
        remove_file(filename)

def write_pipe(pipe_filepath):
    try:
        with open(pipe_filepath, "w") as pout:
            pout.write("<cancelled>")
            print(f"Canceled {pipe_filepath}")
    except Exception:
        pass

def unblock_result_pipe_reader(pipe_filepath):
    print(f"Unlock consumer pipe: {pipe_filepath}")
    unlocking_script = 'bash -c "echo \"[cancelled]\" > ' + pipe_filepath +'"'
    print(f"execute unlocking script: {unlocking_script}")
    proc=subprocess.Popen(unlocking_script, shell=True)
#    proc = multiprocessing.Process(target=write_pipe, args=[pipe_filepath])
    try:
        proc.wait(5)
    except Exception:
        print(f"No one was listening to: {pipe_filepath}. Skip it")
        proc.kill()
    else:
        print(f"Unblocked: {pipe_filepath}")

def unblock_result_pipe_writer(pipe_filepath):
    print(f"Unlock producer pipe: {pipe_filepath}")
    unlocking_script = 'bash -c "echo \"Canceled: `cat ' + pipe_filepath +'`\""'
    print(f"execute unlocking script: {unlocking_script}")
    proc=subprocess.Popen(unlocking_script, shell=True)
#    proc = multiprocessing.Process(target=write_pipe, args=[pipe_filepath])
    try:
        proc.wait(1)
    except Exception:
        print(f"No one was writing to: {pipe_filepath}. Skip it")
        proc.kill()
    else:
        print(f"Unblocked: {pipe_filepath}")

def remove_api_fs_pipes_node(api_root_path, communication_type, req, rtype):
    api_req_directory, api_exec_node_directory = compose_api_fs_request_location_paths(api_root_path, req, rtype)
    api_gui_exec_filename = os.path.join(api_exec_node_directory, api_gui_exec_filename_from_req_type(rtype))
    cli_exec_filename = os.path.join(api_exec_node_directory, "exec")
    result_pipes = filesystem_utils.read_pipes_from_path(api_exec_node_directory, r"^result.*$")

    pipes_to_unblock = []
    if communication_type == "server":
        pipes_to_unblock = [*result_pipes]
        for p in pipes_to_unblock:
            unblock_result_pipe_reader(p)
    elif communication_type == "client":
        pipes_to_unblock = [cli_exec_filename, api_gui_exec_filename]
        for p in pipes_to_unblock:
            unblock_result_pipe_writer(p)

    for p in pipes_to_unblock:
        remove_pipe(p)
    return pipes_to_unblock


def renew_api_pseudo_fs(api_schema_path, communication_type, mount_point):
    schemas_file_list = get_api_schema_files(api_schema_path)
    deleted_pipes = []
    for schema_file in schemas_file_list:
        req_name, request_data = deserialize_api_request_from_schema_file(schema_file)
        req_type = request_data["Method"]
        req_api = request_data["Query"]
        deleted_pipes.extend(remove_api_fs_pipes_node(mount_point, communication_type, req_api, req_type))
    return deleted_pipes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="Remove file-system API pipesnodes based on pseudo-REST API from cfg file"
    )

    parser.add_argument("api_root_dir", help="Path to the root directory incorporated JSON API schema descriptions")
    parser.add_argument("communication_type", help="Which side of communication is to renew: 'server' or 'client'")
    parser.add_argument("mount_point", help="destination to build file-system nodes")
    args = parser.parse_args()

    communication_types = ("server", "client")
    if args.communication_type not in communication_types:
        sys.exit(f"Incorrect 'communication_type', must be one of: {','.join(communication_types)}")

    deleted_files = renew_api_pseudo_fs(args.api_root_dir, args.communication_type, args.mount_point)
    if len(deleted_files):
        print(f"API entry terminated:\n")
        for f in deleted_files:
            print(f"\t{f}")
