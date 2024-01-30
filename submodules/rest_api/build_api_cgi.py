#!/usr/bin/python

"""
Generates `CGI` script for API request serving
"""

import argparse
from argparse import RawTextHelpFormatter
from math import log10

import json
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
from api_gen_utils import file_extension_from_content_type


parser = argparse.ArgumentParser(
    prog="Build REST API serving CGI from JSON schemas",
    formatter_class=RawTextHelpFormatter,
)

parser.add_argument("api_schemas_input_dir", help="Path to the input directory where JSON API schema description files located")
parser.add_argument("domain_name_api_entry", help="build API queries processor for that particular domain")
args = parser.parse_args()

schemas_file_list = get_api_schema_files(args.api_schemas_input_dir)


def get_query_params(params):
    #str_keys = (f"'{k}'" for k in params.keys()).join(", ")
    #str_values = (f"'{v}'" for v in params.values()).join(", ")
    return [ f"    default_params = {json.dumps(params)}",
             r'    query_params = {}',
             f"    for k,v in default_params.items():",
             r'        if not isinstance(v, dict):',
             f"            query_params[k]=request.args.get(k,v)",
             f"    query_params_str=''",
             f"    for k,v in query_params.items():",
             r'        query_params_str +=f"{k}={v} "',
             r'    query_params_str=query_params_str.removesuffix(" ")'
    ]

def generate_cgi_schema(req_api, req_type, output_pipe, params, content_type):
    canonize_api_method_name = req_api.replace(os.sep, "_")
    canonize_api_method_name = canonize_api_method_name.replace('.', '_')

    if len(content_type) != 0:
        response_generator = [
            r'    pout = open(api_result_pipe, "rb")',
            r'    return send_file(io.BytesIO(pout.read()), download_name="pout.{}", mimetype="{}")'.format(file_extension_from_content_type(content_type), content_type),
        ]
    else:
        response_generator = [
            r'    pout = open(api_result_pipe, "r")',
            r'    return f"<p>{pout.read()}</p>"'
        ]

    methods = f"\"{req_type}\""
    make_redirect_url = [""]
    if req_type == "POST":
        # we cannot send post by typing a resource URL. We need for a 'submit' button placed on HTML form instead
        # For each POST-request we just generate the appropriate GET-request which provides us
        # with a submit HTML form
        methods += ", \"GET\""
        make_redirect_url =[ r'    if request.method == "GET":',
                             r'        return f"<form style=\"display: none\" action=\"/{}\" method=\"post\">"+'.format(req_api) + r'"<button type=\"submit\" id=\"button_to_link\"> </button></form><label style=\"text-decoration: underline\" for=\"button_to_link\"> submit {} </label>"'.format(req_api)
        ]

    cgi_schema = [ r'@app.route("/{}",  methods=[{}])'.format(req_api, methods),
                   r'def {}():'.format(canonize_api_method_name),
                   *make_redirect_url,
                   r'    api_query_pipe="/mnt/{}/{}/exec"'.format(req_api, req_type),
                   r'    api_result_pipe="/mnt/{}/{}/{}"'.format(req_api, req_type, output_pipe),
                   r'    pin = open(api_query_pipe, "w")',
                   *get_query_params(params), r'',
                   r'    pin.write(query_params_str)',
                   r'    pin.close()',
                   *response_generator, r''
    ]
    return cgi_schema


for schema_file in schemas_file_list:
    req_name, request_data = decode_api_request_from_schema_file(schema_file)
    req_type = request_data["Method"]
    req_api = request_data["Query"]
    req_params = request_data["Params"]

    content_type=""
    if "Content-Type" in request_data:
        content_type = request_data["Content-Type"]

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

    cgi_content = generate_cgi_schema(req_api, req_type, output_pipe, req_params, content_type)
    for l in cgi_content:
        print(l)
