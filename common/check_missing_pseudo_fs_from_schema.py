#!/usr/bin/python

import argparse
import json
import os
import stat
import sys

sys.path.append('modules')
sys.path.append(os.getenv("MAIN_IMAGE_ENV_SHARED_LOCATION_ENV", ""))

import api_fs_args
import filesystem_utils
from api_deps_utils import get_api_service_dependency_files
from api_schema_utils import gather_api_schemas_from_mount_point
from api_schema_utils import deserialize_api_request_from_schema_file
from api_fs_conventions import get_api_schema_files


parser = argparse.ArgumentParser(
    prog="Traverse across file-system API and check availability of requested API set"
)

parser.add_argument("mount_point", help="Root pseudo fs API mount point")
parser.add_argument("domain_name_api_entry", help="build API queries processor for that particular domain")
parser.add_argument(
    "api_schema_dir_to_find", help="Check presence of this API set"
)
parser.add_argument("--service", help="regex to filter an appropriate services out. Default='.*'", default=r'.*')
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
for must_have_req_name, [must_have_service, must_have_query] in API_dependency_table.items():
    must_have_service = os.path.basename(must_have_service)
    found = False
    for restored_api_request in gathered_fs_API.values():
        if restored_api_request["Query"] == must_have_query["Query"]:
            found = True
    if not found:
        if must_have_service not in missing_API_table.keys():
            missing_API_table[must_have_service] = {}
        must_have_query.pop('Params', None)
        must_have_query.pop('Description', None)
        missing_API_table[must_have_service][must_have_req_name] = must_have_query

if len(missing_API_table) != 0:
    print(json.dumps(missing_API_table))
