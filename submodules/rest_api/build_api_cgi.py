#!/usr/bin/python

"""
Generates `CGI` script for API request serving
"""

import argparse
from argparse import RawTextHelpFormatter
from math import log10
import os
import pathlib
import sys
import stat


sys.path.append(os.getenv('MAIN_IMAGE_ENV_SHARED_LOCATION_ENV', ''))

from filesystem_utils import append_file_mode

import filesystem_utils

from api_gen_utils import compose_api_exec_script_name
from api_gen_utils import compose_api_fs_node_name
from api_gen_utils import get_generated_scripts_path
from api_gen_utils import get_api_schema_files
from api_gen_utils import decode_api_request_from_schema_file


parser = argparse.ArgumentParser(
    prog="Build REST API serving CGI from JSON schemas",
    formatter_class=RawTextHelpFormatter,
)

parser.add_argument("api_schemas_input_dir", help="Path to the input directory where JSON API schema description files located")
parser.add_argument("domain_name_api_entry", help="build API queries processor for that particular domain")
args = parser.parse_args()

schemas_file_list = get_api_schema_files(args.api_schemas_input_dir)


cgi_schema = [ r'@app.route("/{}",  methods=["{}"])',
               r'def {}():',
               r'    pin = open("/mnt/{}/{}/exec", "w")',
               r'    pin.write("0")',
               r'    pin.close()',
               r'    pout = open("/mnt/{}/{}/{}", "r")',
               r'    return f"<p>{pout.read()}</p>"',
               r''

]
for schema_file in schemas_file_list:
    req_name, request_data = decode_api_request_from_schema_file(schema_file)
    req_type = request_data["Method"]
    req_api = request_data["Query"]
    req_params = request_data["Params"]

    domain_entry_pos = req_api.find(args.domain_name_api_entry)
    if domain_entry_pos == -1:
        continue

    # determine output PIPE name extension
    req_fs_leaf_node = os.path.join(req_api, req_type)
    pipes_files = { f for f in os.listdir(req_fs_leaf_node) if stat.S_ISFIFO(os.stat(os.path.join(req_fs_leaf_node, f)).st_mode) }
    output_pipe = ""
    for pf in pipes_files:
        if pf.find("result") != -1:
            output_pipe = pf
            break
    if len(output_pipe) == 0:
        raise Exception(f"Incorrect filesystem API node: {req_fs_leaf_node}.\nIt must contains 'result' pipe")

    req_api = req_api[domain_entry_pos:]

    cgi_content = cgi_schema.copy()
    cgi_content[0] = cgi_content[0].format(req_api, req_type)
    canonize_api_method_name = req_api.replace(os.sep, "_")
    canonize_api_method_name = canonize_api_method_name.replace('.', '_')
    cgi_content[1] = cgi_content[1].format(canonize_api_method_name)
    cgi_content[2] = cgi_content[2].format(req_api, req_type)
    cgi_content[5] = cgi_content[5].format(req_api, req_type, output_pipe)

    for l in cgi_content:
        print(l)
