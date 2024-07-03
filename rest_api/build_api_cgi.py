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

sys.path.append('modules')

import filesystem_utils

from api_schema_utils import deserialize_api_request_from_schema_file
from api_schema_utils import file_extension_from_content_type


parser = argparse.ArgumentParser(
    prog="Build REST API serving CGI from JSON schemas",
    formatter_class=RawTextHelpFormatter,
)

parser.add_argument("api_schemas_input_dir", help="Path to the input directory where JSON API schema description files located")
parser.add_argument("filesystem_api_mount_point", help="Path to the shared mount of filesystem API path")
parser.add_argument("domain_name_api_entry", help="build API queries processor for that particular domain")
args = parser.parse_args()

schemas_file_list = filesystem_utils.read_files_from_path(args.api_schemas_input_dir, r".*\.json$")


def get_query_params(params):
    #str_keys = (f"'{k}'" for k in params.keys()).join(", ")
    #str_values = (f"'{v}'" for v in params.values()).join(", ")
    return [ f"    default_params = {json.dumps(params)}",
            # rest_api always uses SESSION_ID
             r'    query_params = {"SESSION_ID": session_id_value}',
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

def generate_cgi_schema(filesystem_api_mount_point, req_api, req_type, output_pipe, params, content_type):
    canonize_api_method_name = req_api.replace(os.sep, "_")
    canonize_api_method_name = canonize_api_method_name.replace('.', '_')

    if len(content_type) != 0:
        response_generator = [
            r'    out = query.wait_binary_result(session_id_value, 0.1, 30, True)',
            r'    return send_file(io.BytesIO(out), download_name="out.{}", mimetype="{}")'.format(file_extension_from_content_type(content_type), content_type),
        ]
    else:
        response_generator = [
            r'    out = query.wait_result(session_id_value, 0.1, 30, True)',
            r'    return f"<p>{out}</p>"'
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
                   r'    api_query_pipe="/{}/{}/{}/exec"'.format(filesystem_api_mount_point, req_api, req_type),
                   # rest_api always uses SESSION_ID
                   r'    session_id_value=socket.gethostname()',
                   r'    api_result_pipe="/{}/{}_" + session_id_value'.format(filesystem_api_mount_point, output_pipe),
                   r'    query = APIQuery([api_query_pipe, api_result_pipe])',
                   *get_query_params(params), r'',
                   r'    query.execute(query_params_str)',
                   r'    api_result_pipe_timeout_cycles=0',
                   r'    while not (os.path.exists(api_result_pipe) and stat.S_ISFIFO(os.stat(api_result_pipe).st_mode)):',
                   r'        sleep(0.1)',
                   r'        api_result_pipe_timeout_cycles += 1',
                   r'        if api_result_pipe_timeout_cycles >= 30:',
                   r'            return f"<p>\"Filesystem API did not respond\"</p>"',
                   *response_generator, r''
    ]
    return cgi_schema


# print the main page
cgi_main = [ r'@app.route("/api.pmccabe_collector.restapi.org", methods=["GET"])',
             r'def index():',
             r'    with open("rest_api_server/templates/index.md", "r") as readme_file:',
             r'        api_description = readme_file.read()',
             r'        api_description = markdown.markdown(api_description)',
             r'    return render_template("index.html", content_body=api_description)'
]
print("\n".join(cgi_main))
print("")

for schema_file in schemas_file_list:
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
    cgi_content = generate_cgi_schema(args.filesystem_api_mount_point, req_api, req_type, req_fs_output_pipe_name, req_params, content_type)
    for l in cgi_content:
        print(l)
