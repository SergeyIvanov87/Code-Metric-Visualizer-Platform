#!/usr/bin/python

"""
Generates `CGI` script for API request serving
"""

import argparse
from argparse import RawTextHelpFormatter

import pathlib
import sys

sys.path.append('modules')

from api_browser_utils import (canonize, request_fields, query_page_url, flatten_params,
                               load_api_requests, build_discovery_document, build_browser_catalog)

from api_schema_utils import compose_api_queries_pipe_names
from api_schema_utils import file_extension_from_content_type


parser = argparse.ArgumentParser(
    prog="Build REST API serving CGI from JSON schemas",
    formatter_class=RawTextHelpFormatter,
)

parser.add_argument("api_schemas_input_dir", help="Path to the input directory where JSON API schema description files located")
parser.add_argument("filesystem_api_mount_point", help="Path to the shared mount of filesystem API path")
parser.add_argument("domain_name_api_entry", help="build API queries processor for that particular domain")
args = parser.parse_args()

api_requests = load_api_requests(args.api_schemas_input_dir, args.domain_name_api_entry)
discovery_document = build_discovery_document(api_requests, args.domain_name_api_entry)
portal_path = "/" + args.domain_name_api_entry.strip("/")
browser_path = portal_path + "/_browse"
services, ungrouped_queries, browser_queries = build_browser_catalog(
    api_requests, args.domain_name_api_entry, pathlib.Path(args.api_schemas_input_dir) / "index.md"
)


def get_query_params(params):
    return [
        f"    allowed_params = {list(flatten_params(params))!r}",
        '    query_params_str = "SESSION_ID=" + session_id_value',
        '    for name in allowed_params:',
        # Providers read their own parameter files when no override is sent.
        # Forwarding defaults would consume their quoting again at each FIFO
        # hop, corrupting inherited regexes in statistic/view/flamegraph.
        '        if "default" in request.args or name not in request.args:',
        '            continue',
        '        value = request.args[name]',
        r'        if any(character in value for character in ("\n", "\r", "\x00")):',
        '            abort(400, description="Parameters must fit in one filesystem request line")',
        # The filesystem protocol groups with double quotes, not shell quoting.
        # Preserve spaces, literal quotes and backslashes in explicit values.
        r'''        value = '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"' ''',
        '        query_params_str += f" {name}={value}"',
    ]

def generate_cgi_schema(req_api, req_type, fs_pipes, params, content_type):
    canonize_api_method_name = canonize(req_api, req_type)

    if len(content_type) != 0:
        response_generator = [
            r'    try:',
            r'        docker_logger.debug(f"[HTTP] Getting binary result for query: {request.full_path} on pipes:{api_query_pipe},{api_result_pipe}")',
            r'        out = query.wait_binary_result(session_id_value, 0.1, 30, True)',
            r'        return send_file(io.BytesIO(out), download_name="out.{}", mimetype="{}")'.format(file_extension_from_content_type(content_type), content_type),
            r'    except Exception as ex:',
            r'        docker_logger.error(f"[HTTP] Could not get binary result for query: {request.full_path} on pipes:{api_query_pipe},{api_result_pipe}. Exception: {str(ex)}")',
            r'        return f"<p>\"Exception occured, while waiting for a query binary result for as session id: {session_id_value}</p>", 503',
            r'    finally:',
            r'        queries_in_progress -= 1'
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
            r'    finally:',
            r'        queries_in_progress -= 1'
        ]

    methods = f"\"{req_type}\""
    make_redirect_url = [""]
    if req_type == "POST":
        # we cannot send a POST query by typing a resource URL in a browser tab.
        # We need for a 'submit' button placed on HTML form instead
        # For each POST-request we just generate the appropriate GET-request which provides us
        # with a submit HTML form
        methods += ", \"GET\""
        # A real GET operation at this path takes precedence over the POST UI.
        if any(request_fields(data, args.domain_name_api_entry)["query"] == req_api and data["Method"] == "GET"
               for _, data in api_requests):
            methods = '"POST"'
        else:
            page_url = query_page_url(req_api, req_type, args.domain_name_api_entry)
            make_redirect_url = [
                '    if request.method == "GET":',
                f'        return redirect({page_url!r})',
            ]
    methods += ", \"HEAD\""
    make_session_id = [      r'    session_id_value = request.method + "_" + socket.gethostname() + "_" + socket.gethostbyaddr(request.remote_addr)[0]']
    make_query = [           r'    api_query_pipe="/{}"'.format(fs_pipes[0]),
                             r'    api_main_result_pipe="/{}"'.format(fs_pipes[1]),
                             r'    api_result_pipe="/{}_" + session_id_value'.format(fs_pipes[1]),
                             r'    query = APIQuery([api_query_pipe, api_result_pipe])',
                             r'    async_query = APIQueryInterruptible([api_query_pipe, api_main_result_pipe], remove_session_pipe_on_result_done = False)',
                             r'    if not async_query.is_valid():',
                             r'        docker_logger.debug(f"[HTTP] Cannot execute query: {api_query_pipe}, as cannot create a valid APIQueryInterruptible object")',
                             r'        return f"<p>\"Resource is not available at the moment\"</p>", 503'

    ]
    make_head_probe_check =[ r'    if request.method == "HEAD":',
                             r'        queries_in_progress += 1',
                             r'        try:',
                             r'            timeout_ka_probe=30',
                             r'            ka_tag = str(time.time() * 1000)',
                             r'            query_params_str="API_KEEP_ALIVE_CHECK=" + ka_tag + " SESSION_ID=" + session_id_value',
                             r'            try:',
                             r'                docker_logger.debug(f"[HTTP] Execute HEAD query: {request.full_path} on pipes:{api_query_pipe},{api_result_pipe}")',
                             r'                status,timeout_ka_probe = async_query.execute(timeout_ka_probe, query_params_str)',
                             r'                if not status:',
                             r'                    docker_logger.error(f"[HTTP] Cannot send KA_PROBE while executing a query: {request.full_path} on pipes: {api_query_pipe}, {api_result_pipe}")',
                             r'                    return f"<p>\"Resource is not available at the moment (KA probe could not be sent)\"</p>", 503',
                             r'            except Exception as ex:',
                             r'                docker_logger.error(f"[HTTP] Exception occured: {str(ex)}, while executing a query: {request.full_path} on pipes: {api_query_pipe}, {api_result_pipe}")',
                             r'                return f"<p>\"Exception occured: {str(ex)}, while executing a query using pipes: {api_query_pipe}, {api_result_pipe}</p>", 503',
                             r'            status, out, timeout_ka_probe = async_query.wait_result(timeout_ka_probe, session_id_value, 0.1, timeout_ka_probe / 0.1, False)',
                             r'            if not status or out != ka_tag:',
                             r'                docker_logger.error(f"[HTTP] Cannot execute HEAD query: {request.full_path}: KA probes do not match, get: {out}, expected: {ka_tag}. Pipes : {api_query_pipe}, {api_result_pipe}")',
                             r'                return f"<p>\"Resource is not available at the moment (KA probe failed)\"</p>", 503',
                             r'            return "",200',
                             r'        finally:',
                             r'            queries_in_progress -= 1'
    ]

    cgi_schema = [ r'@app.route("/{}",  methods=[{}], strict_slashes=False)'.format(req_api, methods),
                   r'def {}():'.format(canonize_api_method_name),
                   r'    global queries_in_progress',
                   *make_redirect_url,
                   *make_session_id,
                   *make_query,
                   *make_head_probe_check,
                   *get_query_params(params), r'',
                   r'    queries_in_progress += 1',
                   r'    query.execute(query_params_str)',
                   r'    api_result_pipe_timeout_cycles=0',
                   r'    while not (os.path.exists(api_result_pipe) and stat.S_ISFIFO(os.stat(api_result_pipe).st_mode)):',
                   r'        sleep(0.1)',
                   r'        api_result_pipe_timeout_cycles += 1',
                   r'        docker_logger.debug(f"[HTTP] Query: {request.full_path} waiting for a result pipe creation: {api_result_pipe}, cycles: {api_result_pipe_timeout_cycles}")',
                   r'        if api_result_pipe_timeout_cycles >= 30:',
                   r'            queries_in_progress -= 1',
                   r'            docker_logger.error(f"[HTTP] Pipe for query: {request.full_path} by path: {api_result_pipe} has not been created in time")',
                   r'            return f"<p>\"Filesystem API did not respond\"</p>"',
                   *response_generator, r''
    ]
    return cgi_schema


# print the main portal page
cgi_portal_main = [ r'@app.route("/", methods=["GET"], strict_slashes=False)',
             r'def portal():',
             f'    return redirect({portal_path!r})'
]
print("\n".join(cgi_portal_main))
print("")


# print the main page
cgi_main = [ f'BROWSER_UNGROUPED = {ungrouped_queries!r}',
             f'BROWSER_SERVICES = {services!r}',
             f'BROWSER_QUERIES = {browser_queries!r}',
             f'@app.route({portal_path!r}, methods=["GET"], strict_slashes=False)',
             r'def index():',
             f'    return render_template("services.html", services=BROWSER_SERVICES.values(), ungrouped_queries=BROWSER_UNGROUPED, portal_url={portal_path!r})',
             '',
             f'@app.route({browser_path + "/services/<service_name>"!r}, methods=["GET"], strict_slashes=False)',
             'def browse_service(service_name):',
             '    service = BROWSER_SERVICES.get(service_name)',
             '    if service is None:',
             '        abort(404)',
             '    queries = [dict(query, documentation_html=markdown.markdown(query["documentation"])) for query in service["queries"]]',
             f'    return render_template("service.html", service=service, queries=queries, portal_url={portal_path!r})',
             '',
             f'@app.route({browser_path + "/queries/<query_id>"!r}, methods=["GET"], strict_slashes=False)',
             'def browse_query(query_id):',
             '    query = BROWSER_QUERIES.get(query_id)',
             '    if query is None:',
             '        abort(404)',
             '    template = "query_" + query["method"].lower() + ".html"',
             '    return render_template(template, query=query, documentation_html=markdown.markdown(query["documentation"]))',
]
print("\n".join(cgi_main))
print("")
discovery_endpoint = [
    r'@app.route("/.well-known/http-api-routes/v1", methods=["GET"], strict_slashes=False)',
    r'def http_api_routes_discovery():',
    "    return jsonify({})".format(repr(discovery_document)),
]
print("\n".join(discovery_endpoint))
print("")



for req_name, request_data in api_requests:
    fields = request_fields(request_data, args.domain_name_api_entry)
    req_type, req_api, req_params = fields["method"], fields["query"], fields["params"]

    fs_pipes = compose_api_queries_pipe_names(args.filesystem_api_mount_point, request_data)

    content_type = fields["content_type"]
    cgi_content = generate_cgi_schema(req_api, req_type, fs_pipes, req_params, content_type)
    for l in cgi_content:
        print(l)
