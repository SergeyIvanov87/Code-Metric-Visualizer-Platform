#!/usr/bin/python

import argparse
import json
import os
import socket
import stat
import sys
import time

sys.path.append('modules')
sys.path.append(os.getenv("MAIN_IMAGE_ENV_SHARED_LOCATION_ENV", ""))

import api_fs_args
import filesystem_utils
from api_deps_utils import get_api_service_dependency_files
from api_fs_query import APIQueryInterruptible
from api_schema_utils import gather_api_schemas_from_mount_point
from api_schema_utils import deserialize_api_request_from_schema_file
from api_schema_utils import compose_api_queries_pipe_names
from api_fs_conventions import get_api_schema_files
from renew_pseudo_fs_pipes import unblock_result_pipe_reader
from renew_pseudo_fs_pipes import unblock_result_pipe_writer
from renew_pseudo_fs_pipes import remove_pipe

def push_in_table(result_table, service, query_name, query):
    if service not in result_table.keys():
        result_table[service] = {}
        query.pop('Description', None)
        result_table[service][query_name] = query
    return result_table


parser = argparse.ArgumentParser(
    prog="Traverse across file-system API and check availability of requested API set"
)

parser.add_argument("mount_point", help="Root pseudo fs API mount point")
parser.add_argument("domain_name_api_entry", help="build API queries processor for that particular domain")
parser.add_argument(
    "api_schema_dir_to_find", help="Check presence of this API set"
)
parser.add_argument("--service", help="regex to filter an appropriate services out. Default='.*'", default=r'.*')
parser.add_argument("-t", "--timeout", help="How long in seconds waiting on API FS pipes for a service to respond. Default 5s", default=5)
args = parser.parse_args()


# gather available API from pseudo fs
gathered_fs_API = {}
directories_for_markdown = []

gathered_fs_API,directories_for_markdown = gather_api_schemas_from_mount_point(args.mount_point, args.domain_name_api_entry)

schemas_file_list = []
service_api_deps = get_api_service_dependency_files(args.api_schema_dir_to_find, args.service, r".*\.json$")
for schemas_file_array in service_api_deps.values():
    schemas_file_list.extend(schemas_file_array)


API_dependency_table = {}
for service, schema_file_list in service_api_deps.items():
    for schema_file in schema_file_list:
        req_name, request_data = deserialize_api_request_from_schema_file(schema_file)
        API_dependency_table[req_name] = [service, request_data]

missing_API_table={}
API_table_to_KA_check={}
for must_have_req_name, [must_have_service, must_have_query] in API_dependency_table.items():
    must_have_service = os.path.basename(must_have_service)
    found = False
    for restored_api_request in gathered_fs_API.values():
        if restored_api_request["Query"] == must_have_query["Query"]:
            found = True
            API_table_to_KA_check = push_in_table(API_table_to_KA_check, must_have_service, must_have_req_name, must_have_query)
    if not found:
        missing_API_table = push_in_table(missing_API_table, must_have_service, must_have_req_name, must_have_query)


def unblock_query_pipe(pipe_path):
    unblock_result_pipe_writer(pipe_path, False)

    # Do not remove these pipes, as someone may create it at exact time
    # remove_pipe(pipe_path)

def unblock_result_pipe(pipe_path):
    unblock_result_pipe_reader(pipe_path, False)

    # Do not remove these pipes, as someone may create it at exact time
    # remove_pipe(pipe_path)

# keep_alive check of found API
# As they may exist, but be inoperable
# The following code just sends KEEP_ALIVE probe to make sure that someone sits on other sides of these query pipes
timeout_elapsed = float(args.timeout)
for service, queries_data in API_table_to_KA_check.items():
    hostname = socket.gethostname()
    for query_name, req_data in queries_data.items():
        pipes = compose_api_queries_pipe_names(args.mount_point, req_data, hostname)

        # Default APIQuery removes sessioned pipe once result obtained,
        # Here we must not remove any pipe from FS because a current process is not responsible for clearance.
        # While it's  clearing something, an actual owner might creates those pipes simultaneously.
        # In result, our process will delete these actual pipes and break communication
        query = APIQueryInterruptible(pipes, remove_session_pipe_on_result_done = False)
        if not query.is_valid():
            req_data["Error"]=f"FAILED on pipes checking"
            missing_API_table = push_in_table(missing_API_table, service, query_name, req_data)
            continue

        ka_tag = str(time.time() * 1000)

        status,timeout_elapsed = query.execute(unblock_query_pipe, timeout_elapsed, "API_KEEP_ALIVE_CHECK=" + ka_tag + " SESSION_ID=" + hostname)
        if not status:
            req_data["Error"]=f"FAILED on execute. Elapsed timeout: {timeout_elapsed}"
            missing_API_table = push_in_table(missing_API_table, service, query_name, req_data)
            continue

        #TODO Reconsile timeout_elapsed and wait for pipe creation sleep duration and cycles
        status, result, timeout_elapsed = query.wait_result(unblock_result_pipe, timeout_elapsed, hostname, 0.1, timeout_elapsed / 0.1, False)
        if not status or result != ka_tag:
            req_data["Error"]=repr(f"FAILED on wait result. Response: {result}, expected KA tag: {ka_tag}, elapsed timeout: {timeout_elapsed}")
            missing_API_table = push_in_table(missing_API_table, service, query_name, req_data)
            continue


if len(missing_API_table) != 0:
    print(json.dumps(missing_API_table))
