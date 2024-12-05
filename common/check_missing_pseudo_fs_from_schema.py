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
from api_schema_utils import gather_api_schemas_from_mount_point
from api_schema_utils import deserialize_api_request_from_schema_file
from api_fs_conventions import get_api_schema_files


parser = argparse.ArgumentParser(
    prog="Traverse across file-system API and check requested API existence"
)

parser.add_argument("mount_point", help="A project location directory")
parser.add_argument("domain_name_api_entry", help="build API queries processor for that particular domain")
parser.add_argument(
    "api_schema_dir_to_find", help="Check this API on existence"
)
args = parser.parse_args()


# gather available API from pseudo fs
API_table = {}
directories_for_markdown = []
API_table,directories_for_markdown = gather_api_schemas_from_mount_point(args.mount_point, args.domain_name_api_entry)

API_dependency_table = {}
schemas_file_list = get_api_schema_files(args.api_schema_dir_to_find)
for schema_file in schemas_file_list:
    req_name, request_data = deserialize_api_request_from_schema_file(schema_file)
    API_dependency_table[req_name] = request_data

missing_API_table={}
for must_have_req_name, must_have_query in API_dependency_table.items():
    found = False
    for restored_api_request in API_table.values():
        if restored_api_request["Query"] == must_have_query["Query"]:
            found = True
    if not found:
        missing_API_table[must_have_req_name] = must_have_query

if len(missing_API_table) != 0:
    for key, value in missing_API_table.items():
        value.pop('Params', None)
        value.pop('Description', None)
    print(json.dumps(missing_API_table))
