#!/usr/bin/python

#!/usr/bin/python

"""
Generates `CGI` script for API request serving
"""

import argparse

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



@pytest.fixture()
def get_api_schema_files():
    work_dir = os.getenv('WORK_DIR', '')
    project_dir = os.getenv('INITIAL_PROJECT_LOCATION', '')
    api_dir = os.getenv('SHARED_API_DIR', '')

    return filesystem_utils.read_files_from_path(api_dir, ".*\.json$")

def test_filesystem_api_nodes(get_api_schema_files):
    for schema_file in get_api_schema_files:
        req_name, request_data = deserialize_api_request_from_schema_file(schema_file)
        assert req_name
        assert request_data
        assert ("Method", "Query", "Params") in request_data.keys()
    '''
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
    cgi_content = generate_cgi_schema(args.filesystem_api_mount_point, req_api, req_type, req_fs_output_pipe_name, req_params, content_type)
    for l in cgi_content:
        print(l)
    '''
