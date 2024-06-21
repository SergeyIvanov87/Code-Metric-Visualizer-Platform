import json
import os
import pathlib
import pytest
import sys
import stat

from time import sleep

sys.path.append(os.getenv('MODULES', 'modules'))

import filesystem_utils
from api_schema_utils import deserialize_api_request_from_schema_file
from api_schema_utils import file_extension_from_content_type

def get_files(api_files_schema_dir_path, regex):
    return filesystem_utils.read_files_from_path(api_files_schema_dir_path, regex)

def get_api_schema_files(api_files_schema_dir_path):
    return filesystem_utils.read_files_from_path(api_files_schema_dir_path, r".*\.json$")

def get_api_queries(api_files_schema_dir_path, domain_name_api_entry):
    valid_queries_dict = {}

    for schema_file in get_api_schema_files(api_files_schema_dir_path):
        req_name, request_data = deserialize_api_request_from_schema_file(schema_file)
        assert req_name
        assert request_data
        assert "Method" in request_data.keys()
        assert "Query" in request_data.keys()
        assert "Params" in request_data.keys()
        valid_queries_dict[req_name] = request_data

        # filter out non-related queries
        domain_entry_pos = request_data["Query"].find(domain_name_api_entry)
        if domain_entry_pos == -1:
            continue
    return valid_queries_dict

def compose_api_queries_pipe_names(api_mount_dir, query, session_id=""):
    method = query["Method"]
    query_str = query["Query"]
    params = query["Params"]


    # Content-Type is an optional field
    content_type=""
    if "Content-Type" in query:
        content_type = query["Content-Type"]

    if len(session_id) == 0:
        pipes = ("exec", "result" if content_type == "" else "result." + file_extension_from_content_type(content_type))
    else:
        pipes = ("exec", "result_" + session_id  if content_type == "" else "result." + file_extension_from_content_type(content_type) + "_" + session_id)
    pipes = [os.path.join(api_mount_dir, query_str, method, p) for p in pipes]
    return pipes


def wait_until_pipe_exist(pipe_pathname, sleep_between_cycles=0.1, max_cycles_count=30, console_ping=True):
    cycles_count = 0
    while not (os.path.exists(pipe_pathname) and stat.S_ISFIFO(os.stat(pipe_pathname).st_mode)):
        sleep(sleep_between_cycles)
        cycles_count += 1

        if (cycles_count % 10) == 0 and console_ping:
            print(f"pipe '{pipe_pathname}' readiness awaiting is in progress...", file=sys.stdout, flush=True)

        if cycles_count >= max_cycles_count:
            raise RuntimeError(f"Pipe: {pipe_pathname} - hasn't been created during expected timeout: sleep {sleep_between_cycles}, cycles {max_cycles_count}")
