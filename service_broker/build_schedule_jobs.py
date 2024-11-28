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

from api_deps_utils import get_api_service_deps
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

service_api_deps = get_api_service_deps(os.path.join(args.api_schemas_input_dir, r".*\.json$")

schemas_file_list = service_api_deps.values()
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
            full_path_source = os.path.join(args.api_schemas_input_dir,item["source"])
            ordered_schemas_file_list.append(full_path_source)
            jobs_call_condition_table[full_path_source] = item
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

def generate_cron_jobs_schema(filesystem_api_mount_point, req_api, req_type, output_pipe, params, job_control):
    # avoid isung any external scripts/command invocation in crond-scripts
    # it has no utter SHELL-support, hence many scrips/commands are unavaialbe
    # For example, ask `hostname` using python API. It will be able to extract real container hostname
    # as soon as this is used by `init.sh`
    hostname = socket.gethostname()
    full_query_pipe_path = os.path.join(filesystem_api_mount_point, req_api, req_type, "exec")
    full_result_pipe_path = os.path.join(filesystem_api_mount_point, output_pipe)
    full_result_pipe_path = full_result_pipe_path + "_" + hostname
    job_generator_str = '{} && echo "SESSION_ID={}" > {} && while [ ! -p {} ]; do sleep 0.5; echo "wait for pipe {} ready"; done && cat {} && echo "\\"{}\\" completed" && {}'.format(job_control["pre"], hostname, full_query_pipe_path, full_result_pipe_path, full_result_pipe_path, full_result_pipe_path, req_api, job_control["post"])
    return job_generator_str

#  build jobs
jobs_content = []
for schema_file in ordered_schemas_file_list:
    req_name, request_data = deserialize_api_request_from_schema_file(schema_file)
    req_type = request_data["Method"]
    req_api = request_data["Query"]
    req_params = request_data["Params"]

    # filter unrelated API queries
    domain_entry_pos = req_api.find(args.domain_name_api_entry)
    if domain_entry_pos == -1:
        continue

    # Content-Type is an optional field
    content_type=""
    if "Content-Type" in request_data:
        content_type = request_data["Content-Type"]

    # determine output PIPE name extension base on Content-Type
    if content_type == "":
        req_fs_output_pipe_name = os.path.join(req_api, req_type, "result")
        content_type="text/plain"
    else:
        req_fs_output_pipe_name = os.path.join(req_api, req_type, "result." + file_extension_from_content_type(content_type))

    req_api = req_api[domain_entry_pos:]
    jobs_content.append(generate_cron_jobs_schema(args.filesystem_api_mount_point, req_api, req_type, req_fs_output_pipe_name, req_params, jobs_call_condition_table[schema_file]))

if len(jobs_content) != 0:
    print(" && ".join(jobs_content))
