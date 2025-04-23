#!/usr/bin/python

"""
This module gets an API file in text format previously generated from JSON schemna
and generates `services` scripts, which purpose is to provide the related API services
by listening `inotify` events from related pseudo filesystem and launches
an appropriate `executors`
"""

import argparse
from math import log10
import os
import pathlib
import sys
import stat

sys.path.append('modules')

import filesystem_utils

from api_fs_conventions import api_gui_exec_filename_from_req_type
from api_fs_conventions import compose_api_fs_request_location_paths
from api_fs_conventions import compose_api_exec_script_name
from api_fs_conventions import compose_api_help_script_name
from api_fs_conventions import get_api_cli_service_script_path
from api_fs_conventions import get_api_schema_files
from api_fs_conventions import get_api_gui_service_script_path
from api_fs_conventions import get_generated_scripts_path

from api_schema_utils import deserialize_api_request_from_schema_file
from api_schema_utils import file_extension_from_content_type

from api_fs_bash_utils import generate_exec_watchdog_function
from api_fs_bash_utils import exec_watchdog_function
from api_fs_bash_utils import generate_extract_attr_value_from_string
from api_fs_bash_utils import extract_attr_value_from_string

EMPTY_DEV_SCRIPT_MARK = "<TODO: THE SCRIPT IS EMPTY>"

def check_script_valid(path, script_name):
    script_generated_name = compose_api_exec_script_name(script_name)
    script_generated_path = os.path.join(path,script_generated_name)
    with open(script_generated_path, "r") as script:
        for l in script:
            if l == EMPTY_DEV_SCRIPT_MARK:
                raise NotImplementedError(
                    f'Script "{script_name}" must be implemented, path: {script_generated_path}'
                )

    return script_generated_name


def get_fs_watch_event_for_request_type(req_type):
    events = {"GET": "access", "PUT": "modify", "POST": "modify"}
    if req_type not in events.keys():
        raise Exception(
            f"Request type is not supported: {req_type}. Available types are: {events.keys()}"
        )
    return events[req_type]


api_gui_schema = [
    "{} > {}/help 2>&1\n",
    "shopt -s extglob\n",
    "EXT=`${0}/{1} --result_type`\n",
    "inotifywait -m {0} -e {1} --include '{2}' |\n",
    "\twhile read dir action file; do\n",
    '\t\techo "file: ${file}, action; ${action}, dir: ${dir}"\n',
    '\t\tcase "$action" in\n',
    "\t\t\tACCESS|ATTRIB|MODIFY )\n",
    "\t\t\t\tdate=`date +%Y-%m-%dT%H:%M:%S`\n",
    "\t\t\t\ttouch {0}/in_progress\n",
    '\t\t\t\t"${0}/{1}" {2} 0 > {3}${4}\n',
    '\t\t\t\tchmod +rw {0}${1}\n',
    "\t\t\t\trm -f {0}/in_progress\n",
    "\t\t\t;;\n",
    "\t\t\t*)\n",
    "\t\t\t\t;;\n",
    "\t\tesac\n",
    "\tdone\n",
]

api_cli_schema = [
    *generate_exec_watchdog_function(),
    *generate_extract_attr_value_from_string(),
    'echo "CLI SERVER: {0}"\n',
    "api_exec_node_directory={}\n",
    "shopt -s extglob\n",
    "EXT=`${0}/{1} --result_type`\n",
    'ME=$(basename "$0")\n',
    "pipe_result=${api_exec_node_directory}/result${EXT}\n",
    "pipe_request=${api_exec_node_directory}/exec\n",
    "pipe_result_consumer=${pipe_result}\n",
    'SIGNALS="HUP QUIT ABRT KILL EXIT TERM"\n',
    "if [[ -e $pipe_request ]]; then\n",
    "    rm -f $pipe_request\n",
    "fi\n",
    "if [[ -e $pipe_result ]]; then\n",
    "    rm -f $pipe_result\n",
    "fi\n",
    "mkfifo -m 622 $pipe_request\n",
    'trap "rm -f $pipe_request" ${SIGNALS}\n',
    "mkfifo -m 644 $pipe_result\n",
    'trap "rm -f $pipe_result" ${SIGNALS}\n',
    'SESSION_ID_ATTR="SESSION_ID"\n',
    'SESSION_ID_VALUE="#####"\n',
    'API_KEEP_ALIVE_ATTR="API_KEEP_ALIVE_CHECK"\n',
    'API_KEEP_ALIVE_VALUE="@@@@@"\n'
    'declare -A pipe_result_array\n',
    'pipe_result_array[${SESSION_ID_VALUE}]=${pipe_result}\n',
    'declare -A WATCH_PID_ARRAY\n',
    "while true\n",
    "do\n",
    "    REQUEST_NUM=0\n",
    "    while IFS= read -r CMD_READ\n",
    "    do\n",
    "        pipe_result_consumer=${pipe_result}\n",
    '        SESSION_ID_VALUE="#####"\n',
    '        API_KEEP_ALIVE_VALUE="@@@@@"\n',
    '        if [[ -f "${api_exec_node_directory}/in_progress" ]]; then\n',
    '            rm -f "${api_exec_node_directory}/in_progress"\n',
    "        fi\n",
    '        echo "`date +%H:%M:%S:%3N`\t${ME}\trequest ${REQUEST_NUM}"\n',
    "        " + extract_attr_value_from_string() + " ${SESSION_ID_ATTR} \"${CMD_READ}\" \"#####\" '=' SESSION_ID_VALUE\n",
    "        " + extract_attr_value_from_string() + " ${API_KEEP_ALIVE_ATTR} \"${CMD_READ}\" \"@@@@@\" '=' API_KEEP_ALIVE_VALUE\n",
    "        if [ -z ${pipe_result_array[${SESSION_ID_VALUE}]} ]; then\n",
    '            pipe_result_consumer="${pipe_result}_${SESSION_ID_VALUE}"\n',
    "            pipe_result_array[${SESSION_ID_VALUE}]=${pipe_result_consumer}\n",
    "            if [ -e ${pipe_result_consumer} ]; then\n",
    "                rm -f ${pipe_result_consumer}\n",
    "            fi\n",
    "            mkfifo -m 644 ${pipe_result_consumer}\n",
    '            trap "rm -f $pipe_result_consumer" ${SIGNALS}\n',
    "        fi\n",
    "        if [ -z ${WATCH_PID_ARRAY[${SESSION_ID_VALUE}]} ]; then\n",
    "            WATCH_PID_ARRAY[$SESSION_ID_VALUE]=0\n",
    "        fi\n",
    "        pipe_result_consumer=${pipe_result_array[${SESSION_ID_VALUE}]}\n",
    "        if [ ! -p ${pipe_result_consumer} ]; then\n",
    "            rm -f ${pipe_result_consumer}\n",
    "            mkfifo -m 644 ${pipe_result_consumer}\n",
    "        fi\n",
    '        ' + exec_watchdog_function() + " ${WATCH_PID_ARRAY[${SESSION_ID_VALUE}]} ${pipe_result_consumer}\n",
    "        WATCH_PID_ARRAY[${SESSION_ID_VALUE}]=0\n",
    '        echo "`date +%H:%M:%S:%3N`\t${ME}\t`hostname`\tSTART    [${SESSION_ID_VALUE}]: ${api_exec_node_directory}\targs:\t${CMD_READ}"\treqNum:\t${REQUEST_NUM}\n',
    '        touch "${api_exec_node_directory}/in_progress"\n',
    '        if [ ! -z ${API_KEEP_ALIVE_VALUE} ] && [ ${API_KEEP_ALIVE_VALUE} != "@@@@@" ]; then\n',
    '            RESULT_OUT=$(echo -n "${API_KEEP_ALIVE_VALUE}" | base64)\n',
    '        else\n',
    '            RESULT_OUT=$({0}/{1} {2} ', '"${CMD_READ}" | base64)\n',
    '        fi\n',
    '        rm -f ${api_exec_node_directory}/in_progress\n',
    '        (touch ${api_exec_node_directory}/ready && echo "`date +%H:%M:%S:%3N`\t${ME}\t`hostname`\tFINISH    [${SESSION_ID_VALUE}]: ${api_exec_node_directory}\targs:\t${CMD_READ}\treqNum:\t${REQUEST_NUM} " && echo "${RESULT_OUT}" | base64 -d >$pipe_result_consumer && rm -rf ${api_exec_node_directory}/ready && echo "`date +%H:%M:%S:%3N`\t${ME}\t`hostname`\tCONSUMED [${SESSION_ID_VALUE}]: ${api_exec_node_directory} <--- ${pipe_result_consumer}") &\n',
    "        WATCH_PID_ARRAY[${SESSION_ID_VALUE}]=$!\n",
    "        let REQUEST_NUM=${REQUEST_NUM}+1\n",
    "    done <<< `cat $pipe_request`\n",
    "done\n",
    "echo 'Server {0} stopped'\n",
]

def generate_gui_server_content(req_name, req_type, api_req_directory, api_exec_node_directory, content_type):
    req_executor_name = compose_api_exec_script_name(req_name)
    api_gui_schema_concrete = api_gui_schema.copy()
    template_schema_row_index = 0
    api_gui_schema_concrete[template_schema_row_index] = api_gui_schema_concrete[template_schema_row_index].format(
        "${WORK_DIR}/" + compose_api_help_script_name(req_name), api_req_directory
    )

    # determine result type: either from JSON or from script renerated
    template_schema_row_index += 2
    if len(content_type) != 0:
        api_gui_schema_concrete[template_schema_row_index] = "EXT=." + file_extension_from_content_type(content_type) + "\n"
    else:
        api_gui_schema_concrete[template_schema_row_index] = api_gui_schema_concrete[template_schema_row_index].format("{WORK_DIR}",req_executor_name)

    template_schema_row_index += 1
    api_gui_schema_concrete[template_schema_row_index] = api_gui_schema_concrete[template_schema_row_index].format(
        api_exec_node_directory, get_fs_watch_event_for_request_type(req_type), api_gui_exec_filename_from_req_type(req_type) + "$"
    )

    template_schema_row_index += 6
    api_gui_schema_concrete[template_schema_row_index] = api_gui_schema_concrete[template_schema_row_index].format(
        api_exec_node_directory)

    template_schema_row_index += 1
    api_gui_schema_concrete[template_schema_row_index] = api_gui_schema_concrete[template_schema_row_index].format(
        "{WORK_DIR}",
        req_executor_name,
        api_req_directory,
        os.path.join(api_exec_node_directory, "result_${date}"),
        "{EXT}"
    )

    template_schema_row_index += 1
    api_gui_schema_concrete[template_schema_row_index] = api_gui_schema_concrete[template_schema_row_index].format(
        os.path.join(api_exec_node_directory, "result_${date}"),
        "{EXT}"
    )

    template_schema_row_index += 1
    api_gui_schema_concrete[template_schema_row_index] = api_gui_schema_concrete[template_schema_row_index].format(
        api_exec_node_directory)

    return api_gui_schema_concrete

def generate_cli_server_content(req_name, req_api, req_type, content_type, req_exec_script_root_dir= "${WORK_DIR}"):

    api_req_directory, api_exec_node_directory = compose_api_fs_request_location_paths(
            "${SHARED_API_DIR}", req_api, req_type
    )

    req_executor_name = compose_api_exec_script_name(req_name)
    api_cli_schema_concrete = api_cli_schema.copy()

    template_schema_row_index = len(generate_exec_watchdog_function())
    template_schema_row_index += len(generate_extract_attr_value_from_string())
    api_cli_schema_concrete[template_schema_row_index] = api_cli_schema_concrete[template_schema_row_index].format(req_api)
    template_schema_row_index += 1
    api_cli_schema_concrete[template_schema_row_index] = api_cli_schema_concrete[template_schema_row_index].format(api_exec_node_directory
    )

    # determine result type: either from JSON or from script renerated
    template_schema_row_index += 2
    if len(content_type) != 0:
        api_cli_schema_concrete[template_schema_row_index] = "EXT=." + file_extension_from_content_type(content_type) + "\n"
    else:
        api_cli_schema_concrete[template_schema_row_index] = api_cli_schema_concrete[template_schema_row_index].format("{WORK_DIR}",req_executor_name)

    template_schema_row_index += 60
    api_cli_schema_concrete[template_schema_row_index] = api_cli_schema_concrete[template_schema_row_index].format(
        req_exec_script_root_dir,
        req_executor_name,
        api_req_directory
    )
    api_cli_schema_concrete[-1] = api_cli_schema_concrete[-1].format(req_name)
    return api_cli_schema_concrete

def create_gui_server_content_from_schema(req_name, req_schema):
    req_type = req_schema["Method"]
    req_api = req_schema["Query"]
    req_params = req_schema["Params"]

    content_type=""
    if "Content-Type" in req_schema:
        content_type = req_schema["Content-Type"]

    api_req_directory, api_exec_node_directory = compose_api_fs_request_location_paths(
            "${SHARED_API_DIR}", req_api, req_type
    )

    return generate_gui_server_content(req_name, req_type, api_req_directory, api_exec_node_directory, content_type)


def create_cli_server_content_from_schema(req_name, req_schema, req_exec_script_root_dir = "${WORK_DIR}"):
    req_type = req_schema["Method"]
    req_api = req_schema["Query"]
    req_params = req_schema["Params"]

    content_type=""
    if "Content-Type" in req_schema:
        content_type = req_schema["Content-Type"]

    return generate_cli_server_content(req_name, req_api, req_type, content_type, req_exec_script_root_dir)


def build_api_services(api_schema_path, executor_generated_scripts_path, output_services_path):
    generated_api_server_scripts_path = output_services_path
    os.makedirs(generated_api_server_scripts_path, exist_ok=True)

    schemas_file_list = get_api_schema_files(api_schema_path)
    errors_detected = []
    for schema_file in schemas_file_list:
        req_name, request_data = deserialize_api_request_from_schema_file(schema_file)

        try:
            check_script_valid(executor_generated_scripts_path, req_name)
        except Exception as e:
            errors_detected.append(str(e))
            continue

        #generate CLI API server
        cli_server_content = create_cli_server_content_from_schema(req_name, request_data)
        api_server_script_file_path = get_api_cli_service_script_path(generated_api_server_scripts_path, req_name)
        with open(api_server_script_file_path, "w") as server_file:
            server_file.write("#!/bin/bash\n\n")
            server_file.writelines(cli_server_content)
        filesystem_utils.make_file_executable(api_server_script_file_path)


        # generate GUI API listener
        gui_server_content = create_gui_server_content_from_schema(req_name, request_data)
        api_server_script_file_path = get_api_gui_service_script_path(generated_api_server_scripts_path, req_name)
        with open(api_server_script_file_path, "w") as listener_file:
            listener_file.write("#!/bin/bash\n\n")
            listener_file.writelines(gui_server_content)
        filesystem_utils.make_file_executable(api_server_script_file_path)

    if len(errors_detected) != 0:
        raise Exception(
            "Erros detected:\n{}\nScript execdir: {}".format(
                "\n".join(errors_detected), pathlib.Path(__file__).parent.resolve()
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="Build file-system API nodes based on pseudo-REST API from cfg file"
    )

    parser.add_argument("api_root_dir", help="Path to the root directory incorporated JSON API schema descriptions")
    parser.add_argument("generated_exec_script_dir", help="Path to the directory where the api executable scripts were generated")
    parser.add_argument("-o", "--output_dir",
                        help='Output directory where the generated scripts will be placed. Default=\"./{}\"'.format(get_generated_scripts_path()),
                        default=get_generated_scripts_path())

    args = parser.parse_args()

    build_api_services(args.api_root_dir, args.generated_exec_script_dir, args.output_dir)
