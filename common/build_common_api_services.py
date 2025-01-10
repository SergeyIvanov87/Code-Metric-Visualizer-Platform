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

import api_fs_exec_utils
import api_fs_bash_utils

def make_script_dependencies(script):
    file_extension = ".json"
    body = (
        *api_fs_exec_utils.generate_exec_header(), r"",
        *api_fs_bash_utils.generate_extract_attr_value_from_string(), r"",
        *api_fs_bash_utils.generate_add_suffix_if_exist(), r"",
        *api_fs_bash_utils.generate_wait_until_pipe_exist(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        api_fs_bash_utils.extract_attr_value_from_string() + " \"SESSION_ID\" \"${2}\" \"\" '=' SESSION_ID_VALUE", r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'echo "${OVERRIDEN_CMD_ARGS[@]}" | xargs ${OPT_DIR}/get_service_api_deps.py "/package/API"',

    )
    script.writelines(line + "\n" for line in body)


def make_script_unmet_dependencies(script):
    file_extension = ".json"
    body = (
        *api_fs_exec_utils.generate_exec_header(), r"",
        *api_fs_bash_utils.generate_extract_attr_value_from_string(), r"",
        *api_fs_bash_utils.generate_add_suffix_if_exist(), r"",
        *api_fs_bash_utils.generate_wait_until_pipe_exist(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        api_fs_bash_utils.extract_attr_value_from_string() + " \"SESSION_ID\" \"${2}\" \"\" '=' SESSION_ID_VALUE", r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'echo "${OVERRIDEN_CMD_ARGS[@]}" | xargs ${OPT_DIR}/check_missing_pseudo_fs_from_schema.py ${SHARED_API_DIR} "api.pmccabe_collector.restapi.org" ${DEPEND_ON_SERVICES_API_SCHEMA_DIR}',
        # TODO Make  DEPEND_ON_SERVICES_API_SCHEMA_DIR as a function argument
    )
    script.writelines(line + "\n" for line in body)

def build_ask_dependency_api_service(dep_api_schema_file, output_services_path, output_exec_script_path, make_script):
    generated_api_server_scripts_path = output_services_path
    os.makedirs(generated_api_server_scripts_path, exist_ok=True)
    os.makedirs(output_exec_script_path, exist_ok=True)

    req_name, request_data = deserialize_api_request_from_schema_file(dep_api_schema_file)

    #generate CLI API server only
    cli_server_content = build_api_services.create_cli_server_content_from_schema(req_name, request_data)
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
            make_script(script)
        filesystem_utils.make_file_executable(script_generated_path)

    except FileExistsError as e:
        print(
            f'Skipping the script "{req_name}":\n\t"{e}"'
        )
    return api_server_script_file_path, script_generated_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="Build file-system API nodes based on pseudo-REST API from cfg file"
    )

    parser.add_argument("api_schema_dir", help="Path to the root directory incorporated JSON API schema descriptions")
    parser.add_argument("-os", "--output_server_dir",
                        help='Output directory where the generated server scripts will be placed. Default=\"./{}\"'.format(get_generated_scripts_path()),
                        default=get_generated_scripts_path())
    parser.add_argument("-oe", "--output_exec_dir",
                        help='Output directory where the generated execution scripts will be placed. Default=\"./\"',
                        default="./")



    args = parser.parse_args()

    schemas_file_list = get_api_schema_files(args.api_schema_dir)
    for schema_file in schemas_file_list:
        if schema_file.endswith("all_dependencies.json"):
            build_ask_dependency_api_service(schema_file, args.output_server_dir, args.output_exec_dir, make_script_dependencies)
        if schema_file.endswith("unmet_dependencies.json"):
            build_ask_dependency_api_service(schema_file, args.output_server_dir, args.output_exec_dir, make_script_unmet_dependencies)
