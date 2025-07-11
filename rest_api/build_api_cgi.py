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

from api_schema_utils import compose_api_queries_pipe_names
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

def generate_cgi_schema(req_api, req_type, fs_pipes, params, content_type):
    canonize_api_method_name = req_api.replace(os.sep, "_")
    canonize_api_method_name = canonize_api_method_name.replace('.', '_')

    if len(content_type) != 0:
        response_generator = [
            r'    try:',
            r'        docker_logger.debug(f"[HTTP] Getting binary result for query: {request.full_path} on pipes:{api_query_pipe},{api_result_pipe}")',
            r'        out = query.wait_binary_result(session_id_value, 0.1, 30, True)',
            r'        return send_file(io.BytesIO(out), download_name="out.{}", mimetype="{}")'.format(file_extension_from_content_type(content_type), content_type),
            r'    except Exception as ex:',
            r'        docker_logger.error(f"[HTTP] Could not get binary result for query: {request.full_path} on pipes:{api_query_pipe},{api_result_pipe}. Exception: {str(ex)}")',
            r'        return f"<p>\"Exception occured, while waiting for a query binary result for as session id: {session_id_value}</p>", 503',
        ]
    else:
        response_generator = [
            r'    try:',
            r'        docker_logger.debug(f"[HTTP] Getting result for query: {request.full_path} on pipes:{api_query_pipe},{api_result_pipe}")',
            r'        out = query.wait_result(session_id_value, 0.1, 30, True)',
            r'        return f"<p>{out}</p>"'
            r'    except Exception as ex:',
            r'        docker_logger.error(f"[HTTP] Could not get result for query: {request.full_path} on pipes:{api_query_pipe},{api_result_pipe}. Exception: {str(ex)}")',
            r'        return f"<p>\"Exception occured, while waiting for a query result for as session id: {session_id_value}</p>", 503',
        ]

    methods = f"\"{req_type}\""
    make_redirect_url = [""]
    if req_type == "POST":
        # we cannot send a POST query by typing a resource URL in a browser tab.
        # We need for a 'submit' button placed on HTML form instead
        # For each POST-request we just generate the appropriate GET-request which provides us
        # with a submit HTML form
        methods += ", \"GET\""
        make_redirect_url =[ r'    if request.method == "GET":',
                             r'        return f"<form style=\"display: none\" action=\"/{}\" method=\"post\">"+'.format(req_api) + r'"<button type=\"submit\" id=\"button_to_link\"> </button></form><label style=\"text-decoration: underline\" for=\"button_to_link\"> submit {} </label>"'.format(req_api)
        ]
    methods += ", \"HEAD\""
    make_session_id = [      r'    session_id_value = request.method + "_" + socket.gethostname() + "_" + socket.gethostbyaddr(request.remote_addr)[0]']
    make_query = [           r'    api_query_pipe="/{}"'.format(fs_pipes[0]),
                             r'    api_result_pipe="/{}_" + session_id_value'.format(fs_pipes[1]),
                             r'    query = APIQuery([api_query_pipe, api_result_pipe])'
    ]
    make_head_probe_check =[ r'    if request.method == "HEAD":',
                             r'        ka_tag = str(time.time() * 1000)',
                             r'        query_params_str="API_KEEP_ALIVE_CHECK=" + ka_tag + " SESSION_ID=" + session_id_value',
                             r'        try:',
                             r'            docker_logger.debug(f"[HTTP] Execute HEAD query: {request.full_path} on pipes:{api_query_pipe},{api_result_pipe}")',
                             r'            query.execute(query_params_str)',
                             r'        except Exception as ex:',
                             r'            docker_logger.error(f"[HTTP] Exception occured: {str(ex)}, while executing a query: {request.full_path} on pipes: {api_query_pipe}, {api_result_pipe}")',
                             r'            return f"<p>\"Exception occured: {str(ex)}, while executing a query using pipes: {api_query_pipe}, {api_result_pipe}</p>", 503',
                             r'        api_result_pipe_timeout_cycles=0',
                             r'        while not (os.path.exists(api_result_pipe) and stat.S_ISFIFO(os.stat(api_result_pipe).st_mode)):',
                             r'            sleep(0.1)',
                             r'            api_result_pipe_timeout_cycles += 1',
                             r'            if api_result_pipe_timeout_cycles >= 30:',
                             r'                docker_logger.error(f"[HTTP] Cannot execute HEAD query: {request.full_path}, pipes are not available: {api_query_pipe}, {api_result_pipe}")',
                             r'                return f"<p>\"Resource is not available at the moment\"</p>", 503',
                             r'        out = query.wait_result(session_id_value, 0.1, 30, True)',
                             r'        if out != ka_tag:',
                             r'            docker_logger.error(f"[HTTP] Cannot execute HEAD query: {request.full_path}: KA probes do not match, get: {out}, expected: {ka_tag}. Pipes : {api_query_pipe}, {api_result_pipe}")',
                             r'            return f"<p>\"Resource is not available at the moment (KA probe failed)\"</p>", 503',
                             r'        return "",200'
    ]
    cgi_schema = [ r'@app.route("/{}",  methods=[{}])'.format(req_api, methods),
                   r'def {}():'.format(canonize_api_method_name),
                   *make_session_id,
                   *make_query,
                   *make_head_probe_check,
                   *make_redirect_url,
                   *get_query_params(params), r'',
                   r'    query.execute(query_params_str)',
                   r'    api_result_pipe_timeout_cycles=0',
                   r'    while not (os.path.exists(api_result_pipe) and stat.S_ISFIFO(os.stat(api_result_pipe).st_mode)):',
                   r'        sleep(0.1)',
                   r'        api_result_pipe_timeout_cycles += 1',
                   r'        docker_logger.debug(f"[HTTP] Query: {request.full_path} waiting for a result pipe creation: {api_result_pipe}")',
                   r'        if api_result_pipe_timeout_cycles >= 30:',
                   r'            docker_logger.error(f"[HTTP] Pipe for query: {request.full_path} by path: {api_result_pipe} has not been created in time")',
                   r'            return f"<p>\"Filesystem API did not respond\"</p>"',
                   *response_generator, r''
    ]
    return cgi_schema


# print the main portal page
cgi_portal_main = [ r'@app.route("/", methods=["GET"])',
             r'def portal():',
             r'    return redirect("/api.pmccabe_collector.restapi.org")'
]
print("\n".join(cgi_portal_main))
print("")


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

    fs_pipes = compose_api_queries_pipe_names(args.filesystem_api_mount_point, request_data)

    # Content-Type is an optional field
    content_type=""
    if "Content-Type" in request_data:
        content_type = request_data["Content-Type"]

    # determine output PIPE name extension base on Content-Type
    if content_type == "":
        content_type="text/plain"

    req_api = req_api[domain_entry_pos:]
    cgi_content = generate_cgi_schema(req_api, req_type, fs_pipes, req_params, content_type)
    for l in cgi_content:
        print(l)
