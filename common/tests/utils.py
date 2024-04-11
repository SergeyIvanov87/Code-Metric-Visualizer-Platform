import json
import os
import pathlib
import pytest
import sys
import stat


sys.path.append(os.getenv('UTILS', ''))
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

def compose_api_querie_pipe_names(api_mount_dir, query):
    method = query["Method"]
    query_str = query["Query"]
    params = query["Params"]


    # Content-Type is an optional field
    content_type=""
    if "Content-Type" in query:
        content_type = query["Content-Type"]

    pipes = ("exec", "result" if content_type == "" else "result." + file_extension_from_content_type(content_type))
    pipes = [os.path.join(api_mount_dir, query_str, method, p) for p in pipes]
    return pipes
