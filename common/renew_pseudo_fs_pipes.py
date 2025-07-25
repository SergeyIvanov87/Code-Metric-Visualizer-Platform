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

def check_pipe(pipe_filepath):
    if not os.path.exists(pipe_filepath):
        return False

    if not stat.S_ISFIFO(os.stat(pipe_filepath).st_mode):
        os.remove(pipe_filepath)
        return False
    return True

def unblock_result_pipe_reader(pipe_filepath, print_log = True):
    if print_log:
        print(f"Unlock consumer pipe: {pipe_filepath}", file=sys.stdout, flush=True)
    if not check_pipe(pipe_filepath):
        return

    unlocking_script = 'bash -c "echo \"[cancelled]\" > ' + pipe_filepath +'"'
    unblocked_readers_count = 0
    unblocked_attempt_count = 0
    while unblocked_readers_count == unblocked_attempt_count:
        if not check_pipe(pipe_filepath):
            return

        unblocked_attempt_count += 1
        if print_log:
            print(f"execute unlocking script: {unlocking_script}, attempt: {unblocked_attempt_count}", file=sys.stdout, flush=True)
        proc=subprocess.Popen(unlocking_script, shell=True)
        try:
            proc.wait(0.5)
        except Exception:
            if print_log:
                print(f"No one was listening to: {pipe_filepath}. Skip it", file=sys.stdout, flush=True)
            proc.kill()
        else:
            unblocked_readers_count += 1
            if print_log:
                print(f"Unblocked: {pipe_filepath}, clients: {unblocked_readers_count}", file=sys.stdout, flush=True)

def unblock_result_pipe_writer(pipe_filepath, print_log = True):
    if print_log:
        print(f"Unlock producer pipe: {pipe_filepath}", file=sys.stdout, flush=True)
    if not check_pipe(pipe_filepath):
        return

    unlocking_script = 'bash -c "cat ' + pipe_filepath
    if not print_log:
        unlocking_script += " > /dev/null"
    unlocking_script += '"'

    unblocked_writers_count = 0
    unblocked_attempt_count = 0
    while unblocked_writers_count == unblocked_attempt_count:
        if not check_pipe(pipe_filepath):
            return

        unblocked_attempt_count += 1
        if print_log:
            print(f"execute unlocking script: {unlocking_script}, attempt: {unblocked_attempt_count}", file=sys.stdout, flush=True)
        proc=subprocess.Popen(unlocking_script, shell=True)
        try:
            proc.wait(0.5)
        except Exception:
            if print_log:
                print(f"No one was writing to: {pipe_filepath}. Skip it", file=sys.stdout, flush=True)
            proc.kill()
        else:
            unblocked_writers_count += 1
            if print_log:
                print(f"Unblocked: {pipe_filepath}, clients: {unblocked_writers_count}", file=sys.stdout, flush=True)

def remove_api_fs_pipes_node(api_root_path, communication_type, req, rtype):
    api_req_directory, api_exec_node_directory = compose_api_fs_request_location_paths(api_root_path, req, rtype)
    api_gui_exec_filename = os.path.join(api_exec_node_directory, api_gui_exec_filename_from_req_type(rtype))
    cli_exec_filename = os.path.join(api_exec_node_directory, "exec")
    result_pipes = filesystem_utils.read_pipes_from_path(api_exec_node_directory, r"^result.*$")

    sys.stdout.flush()
    pipes_to_unblock = []
    children = []
    if communication_type == "server":
        pipes_to_unblock = [*result_pipes]
        for p in pipes_to_unblock:
            # leverage multiprocessing to unblock pipes simultaneously
            try:
                pid = os.fork()
                if pid == 0:
                    # from child
                    unblock_result_pipe_reader(p)
                    os._exit(0)
                children.append(pid)
            except OSError:
                sys.stderr.write(f"Could not create a child process for unblocking: {communication_type}. Unblock {p} from the main process\n")
                unblock_result_pipe_reader(p)
                pass


    elif communication_type == "client":
        pipes_to_unblock = [cli_exec_filename, api_gui_exec_filename] # api_gui_exec_filename is not pipe, must be skipped
        for p in pipes_to_unblock:
             # leverage multiprocessing to unblock pipes simultaneously
            try:
                pid = os.fork()
                if pid == 0:
                    # from child
                    unblock_result_pipe_writer(p)
                    os._exit(0)
                children.append(pid)
            except OSError:
                sys.stderr.write(f"Could not create a child process for unblocking: {communication_type}. Unblock {p} from the main process\n")
                unblock_result_pipe_writer(p)
                pass

    # we have to wait all children processess before delete pipes/files
    # If we don't wait, then we won't unblock clients & servers
    print(f"Waiting for finishing of child processes: {children}", file=sys.stdout, flush=True)
    for c in children:
        os.waitpid(0, 0)

    print(f"Child processes have finished: {children}", file=sys.stdout, flush=True)
    for p in pipes_to_unblock:
        remove_pipe(p)
    # make sure a regular file doesn't pretend to be a PIPE,
    # it may happens sometimes, when a service is dead, but clients are trying to make queries
    for p in pipes_to_unblock:
        if (os.path.exists(p)):
            remove_file(p)

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
        print(f"API entry terminated:\n{deleted_files}")
