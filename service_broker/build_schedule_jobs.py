#!/usr/bin/python

"""
Generates `CGI` script for API request serving
"""

import argparse
from argparse import RawTextHelpFormatter
from collections import defaultdict
from math import log10

import json
import os
import pathlib
import socket
import sys
import stat

sys.path.append('modules')

import filesystem_utils

from api_deps_utils import get_api_service_dependency_files
from api_schema_utils import compose_api_queries_pipe_names
from api_schema_utils import deserialize_api_request_from_schema_file
from api_schema_utils import file_extension_from_content_type


parser = argparse.ArgumentParser(
    prog="Build CRON scheduling jobs list from API json files",
    formatter_class=RawTextHelpFormatter,
)

parser.add_argument("api_schemas_input_dir", help="Path to the input directory where JSON API schema description files located")
parser.add_argument("filesystem_api_mount_point", help="Path to the shared mount of filesystem API path")
parser.add_argument("domain_name_api_entry", help="build API queries scheduler for that particular domain")

args = parser.parse_args()

def intersection(list_lhs, list_rhs):
    return [ i for i in list_lhs if i in list_rhs ]

service_api_deps = get_api_service_dependency_files(os.path.join(args.api_schemas_input_dir,"deps"), r".*", r".*\.json$")

schemas_file_list = []
for schemas_file_array in service_api_deps.values():
    schemas_file_list.extend(schemas_file_array)

main_api_file_list = filesystem_utils.read_files_from_path(args.api_schemas_input_dir, r".*\.json$")
order_list_file_path = os.path.join(args.api_schemas_input_dir, "service_broker_queries_order_list.json")
if order_list_file_path not in main_api_file_list:
    raise Exception(f"Required file \"{order_list_file_path}\" is absent. It MUST contain an order of queries to build a schedule up. Please add it")

# fill in queries call-order
ordered_schemas_file_list = []
jobs_call_condition_table = defaultdict(dict)
with open(order_list_file_path, "r") as order_list_file:
    try:
        order_list_file_data = json.load(order_list_file)
        if "jobs" not in order_list_file_data.keys():
            raise Exception(f"File \"{order_list_file_path}\" MUST contain \"jobs\" array, got:\n {order_list_file_data}")

        for item in order_list_file_data["jobs"]:
            if "source" not in item.keys():
                raise Exception(f"In file \"{order_list_file_path}\" \"jobs\" an array item must contain MAJOR field \"source\" with query file location, got:\n {item}")
            for schema_file in schemas_file_list:
                if schema_file.endswith(item["source"]):
                    ordered_schemas_file_list.append(schema_file)
                    jobs_call_condition_table[schema_file] = item
    except json.decoder.JSONDecodeError as e:
        raise Exception(f"Error: {str(e)} in file: {order_list_file_path}")

# test consistency
if len(schemas_file_list) != len(ordered_schemas_file_list) or len(intersection(ordered_schemas_file_list, schemas_file_list)) != len(schemas_file_list):
    raise Exception(f"API query files presented in \"{args.api_schemas_input_dir}\" and required by schema in \"{order_list_file_path}\" are differ:\n{schemas_file_list}\nvs\n{ordered_schemas_file_list}\nPlease fix it, maybe you forgot something.")

def get_query_params(params):
    #str_keys = (f"'{k}'" for k in params.keys()).join(", ")
    #str_values = (f"'{v}'" for v in params.values()).join(", ")
    return [ f"    default_params = {json.dumps(params)}",
             r'    query_params = {}',
             r'    if "default" in request.args:',
             r'         for k,v in default_params.items():',
             r'            if not isinstance(v, dict):',
             f"                query_params[k]=v",
             r'    else:',
             r'        # allow only params from JSON schema ',
             f"        for k,v in default_params.items():",
             r'            # pass params from query, if exist',
             r'            if not isinstance(v, dict) and k in request.args:',
             f"                query_params[k]=request.args.get(k,v)",
             f"    query_params_str=''",
             f"    for k,v in query_params.items():",
             r'        query_params_str +=f"{k}={v} "',
             r'    query_params_str=query_params_str.removesuffix(" ")'
    ]

def generate_cron_jobs_schema(req_api, fs_pipes, job_control):
    # avoid isung any external scripts/command invocation in crond-scripts
    # it has no utter SHELL-support, hence many scrips/commands are unavaialbe
    # For example, ask `hostname` using python API. It will be able to extract real container hostname
    # as soon as this is used by `init.sh`
    hostname = socket.gethostname()
    full_query_pipe_path, full_result_pipe_path = fs_pipes
    full_result_pipe_path = full_result_pipe_path + "_" + hostname
    job_generator_str = '{} && echo "SESSION_ID={}" > {} && while [ ! -p {} ]; do sleep 0.5; echo "wait for pipe {} ready"; done && cat {} && echo "\\"{}\\" completed" && {}'.format(job_control["pre"], hostname, full_query_pipe_path, full_result_pipe_path, full_result_pipe_path, full_result_pipe_path, req_api, job_control["post"])
    return job_generator_str

#  build jobs
jobs_content = []
for schema_file in ordered_schemas_file_list:
    req_name, request_data = deserialize_api_request_from_schema_file(schema_file)
    req_api = request_data["Query"]

    # filter unrelated API queries
    domain_entry_pos = req_api.find(args.domain_name_api_entry)
    if domain_entry_pos == -1:
        continue

    req_fs_pipes = compose_api_queries_pipe_names(args.filesystem_api_mount_point, request_data)
    req_api = req_api[domain_entry_pos:]
    jobs_content.append(generate_cron_jobs_schema(req_api, req_fs_pipes, jobs_call_condition_table[schema_file]))

if len(jobs_content) != 0:
    print(" && ".join(jobs_content))
