#!/usr/bin/python


import argparse
import os
import sys

sys.path.append('modules')

import filesystem_utils
import build_api_services

from api_fs_conventions import compose_api_exec_script_name
from api_fs_conventions import get_api_cli_service_script_path
from api_fs_conventions import get_api_schema_files
from api_fs_conventions import get_generated_scripts_path

from api_schema_utils import deserialize_api_request_from_schema_file
from api_schema_utils import file_extension_from_content_type_or_default

import api_fs_exec_utils
import api_fs_bash_utils

def make_script_proxy_query(script, request_data):
    desired_file_ext = file_extension_from_content_type_or_default(request_data, "")
    file_extension = ""
    if len(desired_file_ext) != 0:
        file_extension = "." + desired_file_ext

    body = [
        *api_fs_exec_utils.generate_exec_header(), r"",
        *api_fs_bash_utils.generate_extract_attr_value_from_string(), r"",
        *api_fs_bash_utils.generate_add_suffix_if_exist(), r"",
        *api_fs_bash_utils.generate_wait_until_pipe_exist(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        api_fs_bash_utils.extract_attr_value_from_string() + " \"SESSION_ID\" \"${2}\" \"\" '=' SESSION_ID_VALUE", r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'CURL_GET_PARAMS=""',
        r'let i=0',
        r'for a in ${OVERRIDEN_CMD_ARGS[@]}',
        r'do',
        r'  if [ $i -eq 0 ] ; then',
        r'      CURL_GET_PARAMS="${CURL_GET_PARAMS} -d \"${a}"',
        r'      let i=1',
        r'  else',
        r'      CURL_GET_PARAMS="${CURL_GET_PARAMS}=${a}\""',
        r'      let i=0',
        r'  fi',
        r'done',
        r'#cut root /api path, as it must not be present in HTTP query',
        r'API_REL_NODE=${API_NODE#$SHARED_API_DIR}'
    ]
    if "Method" in request_data:
        if "GET" == request_data["Method"]:
            body.append(r'curl --get ${CURL_GET_PARAMS} ${DOWNSTREAM_SERVICE_NETWORK_ADDR}/${API_REL_NODE}')
        elif "PUT" == request_data["Method"]:
            body.append(r'curl ${CURL_GET_PARAMS} -X PUT ${DOWNSTREAM_SERVICE_NETWORK_ADDR}/${API_REL_NODE}')
        elif "POST" == request_data["Method"]:
            body.append(r'curl ${CURL_GET_PARAMS} -X POST ${DOWNSTREAM_SERVICE_NETWORK_ADDR}/${API_REL_NODE}')
        else:
            raise RuntimeError(f"Cannot generate script: {script}, as \"Method\" of a request is not supported: {request_data}. Abort")
    script.writelines(line + "\n" for line in body)


def build_proxy_api_service(dep_api_schema_file, output_services_path, output_exec_script_path, make_script):
    generated_api_server_scripts_path = output_services_path
    os.makedirs(generated_api_server_scripts_path, exist_ok=True)
    os.makedirs(output_exec_script_path, exist_ok=True)

    req_name, request_data = deserialize_api_request_from_schema_file(dep_api_schema_file)

    #generate CLI API server only
    cli_server_content = build_api_services.create_cli_server_content_from_schema(req_name, request_data, output_exec_script_path)
    api_server_script_file_path = build_api_services.get_api_cli_service_script_path(generated_api_server_scripts_path, req_name)
    with open(api_server_script_file_path, "w") as server_file:
        server_file.write("#!/bin/bash\n\n")
        server_file.writelines(cli_server_content)
    filesystem_utils.make_file_executable(api_server_script_file_path)

    # generate execution script
    try:
        script_name_generated = compose_api_exec_script_name(req_name)
        script_generated_path = os.path.join(output_exec_script_path, script_name_generated)

        with open(script_generated_path, "x") as script:
            make_script(script, request_data)
        filesystem_utils.make_file_executable(script_generated_path)

    except FileExistsError as e:
        print(
            f'Skipping the script "{req_name}":\n\t"{e}"'
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="Build file-system API nodes based on pseudo-REST API from cfg file"
    )

    parser.add_argument("api_schema_dir", help="Path to the root directory incorporated services and their JSON API schema descriptions")
    parser.add_argument("-os", "--output_server_dir",
                        help='Output directory where the generated server scripts will be placed. Default=\"./{}\"'.format(get_generated_scripts_path()),
                        default=get_generated_scripts_path())
    parser.add_argument("-oe", "--output_exec_dir",
                        help='Output directory where the generated execution scripts will be placed. Default=\"./\"',
                        default="./")



    args = parser.parse_args()

    schemas_file_list = get_api_schema_files(args.api_schema_dir)
    for schema_file in schemas_file_list:
        build_proxy_api_service(schema_file, args.output_server_dir, args.output_exec_dir, make_script_proxy_query)
