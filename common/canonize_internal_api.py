#!/usr/bin/python


import argparse
import os
import pathlib
import sys
import stat

sys.path.append('modules')

from api_fs_conventions import get_api_schema_files

from api_schema_utils import deserialize_api_request_from_schema_file
from api_schema_utils import serialize_api_request_to_schema_file
import api_deps_utils


def canonize_internal_request(api_schema_file, service_full_name):
    req_name, request_data = deserialize_api_request_from_schema_file(api_schema_file)
    request_data["Query"] = api_deps_utils.canonize_relative_api_req(service_full_name, request_data["Query"])
    serialize_api_request_to_schema_file(api_schema_file, request_data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="Build file-system API nodes based on pseudo-REST API from cfg file"
    )

    parser.add_argument("api_schema_dir", help="Path to the root directory incorporated JSON API schema descriptions")
    parser.add_argument("service_full_name", help="")
    args = parser.parse_args()

    schemas_file_list = get_api_schema_files(args.api_schema_dir)
    for schema_file in schemas_file_list:
         canonize_internal_request(schema_file, args.service_full_name)
