#!/usr/bin/python

#!/usr/bin/python

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
from settings import Settings

global_settings = Settings()

def get_api_schema_files():
    global global_settings
    return filesystem_utils.read_files_from_path("/API", ".*\.json$")

def get_api_queries():
    valid_queries_dict = {}
    global global_settings

    for schema_file in get_api_schema_files():
        req_name, request_data = deserialize_api_request_from_schema_file(schema_file)
        assert req_name
        assert request_data
        assert "Method" in request_data.keys()
        assert "Query" in request_data.keys()
        assert "Params" in request_data.keys()
        valid_queries_dict[req_name] = request_data

        # filter out non-related queries
        domain_entry_pos = request_data["Query"].find(global_settings.domain_name_api_entry)
        if domain_entry_pos == -1:
            continue
    return valid_queries_dict

testdata = list(get_api_queries().items())

@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_nodes(name, query):
    global global_settings
    method = query["Method"]
    query_str = query["Query"]
    params = query["Params"]

    # Content-Type is an optional field
    content_type=""
    if "Content-Type" in query:
        content_type = query["Content-Type"]

    pipes = ["exec", "result" if content_type == "" else "result." + file_extension_from_content_type(content_type)]
    pipes = [os.path.join(global_settings.api_dir, query_str, method, p) for p in pipes]

    # check that special files are really pipes
    for p in pipes:
        assert stat.S_ISFIFO(os.stat(p).st_mode)
