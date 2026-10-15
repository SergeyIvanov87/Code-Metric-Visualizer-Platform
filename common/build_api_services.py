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
from api_fs_bash_utils import generate_unblock_query_pipe_writers_by_owner
from api_fs_bash_utils import unblock_query_pipe_writers_by_owner
from api_fs_bash_utils import generate_unblock_result_pipe_reader_by_owner
from api_fs_bash_utils import unblock_result_pipe_readers_by_owner
from api_fs_bash_utils import generate_unblock_readers_of_result_pipe_array_by_owner
from api_fs_bash_utils import unblock_readers_of_result_pipe_array_by_owner

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
    "EXT=`{0}/{1} --result_type`\n",
    "inotifywait -m {0} -e {1} --include '{2}' |\n",
    "\twhile read dir action file; do\n",
    '\t\techo "file: ${file}, action; ${action}, dir: ${dir}"\n',
    '\t\tcase "$action" in\n',
    "\t\t\tACCESS|ATTRIB|MODIFY )\n",
    "\t\t\t\tdate=`date +%Y-%m-%dT%H:%M:%S`\n",
    "\t\t\t\ttouch {0}/in_progress\n",
    '\t\t\t\t"{0}/{1}" {2} 0 > {3}${4}\n',
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
    *generate_unblock_query_pipe_writers_by_owner(),
    *generate_unblock_result_pipe_reader_by_owner(),
    *generate_unblock_readers_of_result_pipe_array_by_owner(),
    'echo "CLI SERVER: {0}"\n',
    "api_exec_node_directory={}\n",
    "shopt -s extglob\n",
    "EXT=`{0}/{1} --result_type`\n",
    'ME=$(basename "$0")\n',
    "pipe_result=${api_exec_node_directory}/result${EXT}\n",
    "pipe_request=${api_exec_node_directory}/exec\n",
    "pipe_result_consumer=${pipe_result}\n",
    'SIGNALS="HUP QUIT ABRT KILL EXIT TERM"\n',
    "if [[ -e $pipe_request ]]; then\n",
    "    " + unblock_query_pipe_writers_by_owner() + " $pipe_request\n",
    "fi\n",
    "if [[ -e $pipe_result ]]; then\n",
    "    " + unblock_result_pipe_readers_by_owner() + " $pipe_result\n",
    "fi\n",
    unblock_readers_of_result_pipe_array_by_owner() + " ${api_exec_node_directory}/result*\n",
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
    "    done <<< `cat $pipe_request || if [ $? != 0 ]; then mkfifo -m 622 ${pipe_request}; fi`\n",
    "done\n",
    "echo 'Server {0} stopped'\n",
]

def generate_gui_server_content(req_name, req_type, api_req_directory, api_exec_node_directory, content_type, req_exec_script_root_dir= "${WORK_DIR}"):
    req_executor_name = compose_api_exec_script_name(req_name)
    api_gui_schema_concrete = api_gui_schema.copy()
    template_schema_row_index = 0
    api_gui_schema_concrete[template_schema_row_index] = api_gui_schema_concrete[template_schema_row_index].format(
        req_exec_script_root_dir + "/" + compose_api_help_script_name(req_name), api_req_directory
    )

    # determine result type: either from JSON or from script renerated
    template_schema_row_index += 2
    if len(content_type) != 0:
        api_gui_schema_concrete[template_schema_row_index] = "EXT=." + file_extension_from_content_type(content_type) + "\n"
    else:
        api_gui_schema_concrete[template_schema_row_index] = api_gui_schema_concrete[template_schema_row_index].format(req_exec_script_root_dir, req_executor_name)

    template_schema_row_index += 1
    api_gui_schema_concrete[template_schema_row_index] = api_gui_schema_concrete[template_schema_row_index].format(
        api_exec_node_directory, get_fs_watch_event_for_request_type(req_type), api_gui_exec_filename_from_req_type(req_type) + "$"
    )

    template_schema_row_index += 6
    api_gui_schema_concrete[template_schema_row_index] = api_gui_schema_concrete[template_schema_row_index].format(
        api_exec_node_directory)

    template_schema_row_index += 1
    api_gui_schema_concrete[template_schema_row_index] = api_gui_schema_concrete[template_schema_row_index].format(
        req_exec_script_root_dir,
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

def generate_parallel_session_functions(
    req_exec_script_root_dir, req_executor_name, api_req_directory
):
    """Generate helpers for concurrent requests serialized by SESSION_ID."""
    return [
        'parallel_request_executor="{}"\n'.format(
            os.path.join(req_exec_script_root_dir, req_executor_name)
        ),
        'parallel_api_request_directory="{}"\n'.format(api_req_directory),
        "parallel_remove_request_state() {\n",
        '    local request_state="${1}"\n',
        '    rm -f -- "${request_state}/handler.pid" "${request_state}/result_writer.pid" \\\n',
        '        "${request_state}/result_ready" "${request_state}/done"\n',
        '    rmdir -- "${request_state}" 2>/dev/null || true\n',
        "}\n",
        "parallel_prune_finished_requests() {\n",
        '    local session_id=""\n',
        '    local request_state=""\n',
        '    for session_id in "${!PARALLEL_REQUEST_STATE[@]}"; do\n',
        '        request_state="${PARALLEL_REQUEST_STATE[${session_id}]}"\n',
        '        if [[ ! -d "${request_state}" || -e "${request_state}/done" ]]; then\n',
        '            parallel_remove_request_state "${request_state}"\n',
        '            unset "PARALLEL_REQUEST_STATE[${session_id}]"\n',
        "        fi\n",
        "    done\n",
        "}\n",
        "parallel_wait_for_previous_request() {\n",
        '    local previous_state="${1}"\n',
        '    local result_fifo="${2}"\n',
        '    local previous_handler_pid=""\n',
        '    local writer_pid=""\n',
        '    local drain_pid=""\n',
        '    local attempts=0\n',
        '    if [[ -z "${previous_state}" || ! -d "${previous_state}" ]]; then\n',
        "        return\n",
        "    fi\n",
        '    while [[ -d "${previous_state}" && ! -e "${previous_state}/done" ]]; do\n',
        '        if [[ -r "${previous_state}/handler.pid" ]]; then\n',
        '            IFS= read -r previous_handler_pid < "${previous_state}/handler.pid"\n',
        '            if [[ -n "${previous_handler_pid}" ]] && ! kill -0 "${previous_handler_pid}" 2>/dev/null; then\n',
        '                touch "${previous_state}/done"\n',
        "                continue\n",
        "            fi\n",
        "        fi\n",
        '        if [[ -e "${previous_state}/result_ready" && -r "${previous_state}/result_writer.pid" ]]; then\n',
        '            IFS= read -r writer_pid < "${previous_state}/result_writer.pid"\n',
        '            if [[ -n "${writer_pid}" ]] && kill -0 "${writer_pid}" 2>/dev/null; then\n',
        "                timeout 2 /bin/bash -c 'cat \"$1\" >/dev/null 2>&1' _ \"${result_fifo}\" &\n",
        '                drain_pid=$!\n',
        '                attempts=0\n',
        '                while kill -0 "${writer_pid}" 2>/dev/null && (( attempts < 40 )); do\n',
        "                    sleep 0.05\n",
        '                    ((attempts += 1))\n',
        "                done\n",
        '                if kill -0 "${writer_pid}" 2>/dev/null; then\n',
        '                    kill "${writer_pid}" 2>/dev/null || true\n',
        '                    attempts=0\n',
        '                    while kill -0 "${writer_pid}" 2>/dev/null && (( attempts < 20 )); do\n',
        "                        sleep 0.05\n",
        '                        ((attempts += 1))\n',
        "                    done\n",
        '                    if kill -0 "${writer_pid}" 2>/dev/null; then\n',
        '                        kill -KILL "${writer_pid}" 2>/dev/null || true\n',
        "                    fi\n",
        "                fi\n",
        '                wait "${drain_pid}" 2>/dev/null || true\n',
        "            fi\n",
        "        fi\n",
        "        sleep 0.05\n",
        "    done\n",
        '    parallel_remove_request_state "${previous_state}"\n',
        "}\n",
        "parallel_session_request() {\n",
        '    local command="${1}"\n',
        '    local request_num="${2}"\n',
        '    local session_id="${3}"\n',
        '    local keep_alive_value="${4}"\n',
        '    local result_fifo="${5}"\n',
        '    local previous_state="${6}"\n',
        '    local request_state="${7}"\n',
        '    local result_out=""\n',
        '    local result_writer_pid=""\n',
        # The dispatcher owns these descriptors. Close the copies inherited by
        # this background subshell so it cannot keep accepting FIFO writers
        # after the dispatcher exits.
        '    exec {PARALLEL_REQUEST_KEEPALIVE_FD}>&-\n',
        '    exec {PARALLEL_REQUEST_READ_FD}<&-\n',
        '    trap \'touch "${request_state}/done"\' EXIT\n',
        '    parallel_wait_for_previous_request "${previous_state}" "${result_fifo}"\n',
        '    echo "`date +%H:%M:%S:%3N`\\t${ME}\\t`hostname`\\tSTART    [${session_id}]: ${api_exec_node_directory}\\targs:\\t${command}\\treqNum:\\t${request_num}"\n',
        '    if [[ -n "${keep_alive_value}" && "${keep_alive_value}" != "@@@@@" ]]; then\n',
        '        result_out=$(printf \'%s\' "${keep_alive_value}" | base64)\n',
        "    else\n",
        '        result_out=$("${parallel_request_executor}" "${parallel_api_request_directory}" "${command}" | base64)\n',
        "    fi\n",
        '    echo "`date +%H:%M:%S:%3N`\\t${ME}\\t`hostname`\\tFINISH    [${session_id}]: ${api_exec_node_directory}\\targs:\\t${command}\\treqNum:\\t${request_num}"\n',
        '    printf \'%s\\n\' "${result_out}" | base64 -d > "${result_fifo}" &\n',
        '    result_writer_pid=$!\n',
        '    printf \'%s\\n\' "${result_writer_pid}" > "${request_state}/result_writer.pid"\n',
        '    touch "${request_state}/result_ready"\n',
        '    if wait "${result_writer_pid}"; then\n',
        '        echo "`date +%H:%M:%S:%3N`\\t${ME}\\t`hostname`\\tCONSUMED [${session_id}]: ${api_exec_node_directory} <--- ${result_fifo}"\n',
        "    else\n",
        '        echo "`date +%H:%M:%S:%3N`\\t${ME}\\t`hostname`\\tRESET    [${session_id}]: ${api_exec_node_directory} <--- ${result_fifo}"\n',
        "    fi\n",
        "}\n",
    ]


def generate_cli_server_content(
    req_name,
    req_api,
    req_type,
    content_type,
    req_exec_script_root_dir="${WORK_DIR}",
    parallel_by_session=False,
):

    api_req_directory, api_exec_node_directory = compose_api_fs_request_location_paths(
            "${SHARED_API_DIR}", req_api, req_type
    )

    req_executor_name = compose_api_exec_script_name(req_name)
    api_cli_schema_concrete = api_cli_schema.copy()

    template_schema_row_index = len(generate_exec_watchdog_function())
    template_schema_row_index += len(generate_extract_attr_value_from_string())
    template_schema_row_index += len(generate_unblock_query_pipe_writers_by_owner())
    template_schema_row_index += len(generate_unblock_result_pipe_reader_by_owner())
    template_schema_row_index += len(generate_unblock_readers_of_result_pipe_array_by_owner())
    api_cli_schema_concrete[template_schema_row_index] = api_cli_schema_concrete[template_schema_row_index].format(req_api)
    template_schema_row_index += 1
    api_cli_schema_concrete[template_schema_row_index] = api_cli_schema_concrete[template_schema_row_index].format(api_exec_node_directory
    )

    # determine result type: either from JSON or from script renerated
    template_schema_row_index += 2
    if len(content_type) != 0:
        api_cli_schema_concrete[template_schema_row_index] = "EXT=." + file_extension_from_content_type(content_type) + "\n"
    else:
        api_cli_schema_concrete[template_schema_row_index] = api_cli_schema_concrete[template_schema_row_index].format(req_exec_script_root_dir,req_executor_name)

    template_schema_row_index += 61
    api_cli_schema_concrete[template_schema_row_index] = api_cli_schema_concrete[template_schema_row_index].format(
        req_exec_script_root_dir,
        req_executor_name,
        api_req_directory
    )
    api_cli_schema_concrete[-1] = api_cli_schema_concrete[-1].format(req_name)

    if parallel_by_session:
        helper_index = len(generate_exec_watchdog_function())
        helper_index += len(generate_extract_attr_value_from_string())
        helper_index += len(generate_unblock_query_pipe_writers_by_owner())
        helper_index += len(generate_unblock_result_pipe_reader_by_owner())
        helper_index += len(generate_unblock_readers_of_result_pipe_array_by_owner())
        api_cli_schema_concrete[helper_index:helper_index] = generate_parallel_session_functions(
            req_exec_script_root_dir, req_executor_name, api_req_directory
        )

        while_index = api_cli_schema_concrete.index("while true\n")
        api_cli_schema_concrete[while_index:while_index + 4] = [
            'parallel_session_state_root=$(mktemp -d "${TMPDIR:-/tmp}/${ME}.parallel-session-state.XXXXXX")\n',
            "declare -A PARALLEL_REQUEST_STATE\n",
            "PARALLEL_REQUEST_COUNTER=0\n",
            # Keep one reader open for the dispatcher lifetime. The private
            # write descriptor prevents EOF between external FIFO writers.
            # Separate descriptors avoid relying on Linux-specific FIFO O_RDWR
            # behavior.
            'exec {PARALLEL_REQUEST_READ_FD}<"${pipe_request}"\n',
            'exec {PARALLEL_REQUEST_KEEPALIVE_FD}>"${pipe_request}"\n',
            "REQUEST_NUM=0\n",
            'while IFS= read -r -u "${PARALLEL_REQUEST_READ_FD}" CMD_READ\n',
        ]

        batch_end_line = (
            "    done <<< `cat $pipe_request || if [ $? != 0 ]; "
            "then mkfifo -m 622 ${pipe_request}; fi`\n"
        )
        batch_end_index = api_cli_schema_concrete.index(batch_end_line)
        api_cli_schema_concrete[batch_end_index:batch_end_index + 2] = [
            "done\n",
            'exec {PARALLEL_REQUEST_KEEPALIVE_FD}>&-\n',
            'exec {PARALLEL_REQUEST_READ_FD}<&-\n',
        ]

        watchdog_line = (
            "        "
            + exec_watchdog_function()
            + " ${WATCH_PID_ARRAY[${SESSION_ID_VALUE}]} ${pipe_result_consumer}\n"
        )
        watchdog_index = api_cli_schema_concrete.index(watchdog_line)
        api_cli_schema_concrete[watchdog_index:watchdog_index] = [
            '        ((PARALLEL_REQUEST_COUNTER += 1))\n',
            '        if (( PARALLEL_REQUEST_COUNTER % 64 == 0 )); then\n',
            '            parallel_prune_finished_requests\n',
            "        fi\n",
            '        parallel_request_state=$(mktemp -d "${parallel_session_state_root}/request.XXXXXX")\n',
            '        parallel_previous_state=${PARALLEL_REQUEST_STATE[${SESSION_ID_VALUE}]-}\n',
            '        PARALLEL_REQUEST_STATE[${SESSION_ID_VALUE}]="${parallel_request_state}"\n',
            '        parallel_session_request "${CMD_READ}" "${REQUEST_NUM}" "${SESSION_ID_VALUE}" \\\n',
            '            "${API_KEEP_ALIVE_VALUE}" "${pipe_result_consumer}" \\\n',
            '            "${parallel_previous_state}" "${parallel_request_state}" &\n',
            '        printf \'%s\\n\' "$!" > "${parallel_request_state}/handler.pid"\n',
            '        ((REQUEST_NUM += 1))\n',
            "        continue\n",
        ]

    return api_cli_schema_concrete

def create_gui_server_content_from_schema(req_name, req_schema, req_exec_script_root_dir = "${WORK_DIR}"):
    req_type = req_schema["Method"]
    req_api = req_schema["Query"]
    req_params = req_schema["Params"]

    content_type=""
    if "Content-Type" in req_schema:
        content_type = req_schema["Content-Type"]

    api_req_directory, api_exec_node_directory = compose_api_fs_request_location_paths(
            "${SHARED_API_DIR}", req_api, req_type
    )

    return generate_gui_server_content(req_name, req_type, api_req_directory, api_exec_node_directory, content_type, req_exec_script_root_dir)


def create_cli_server_content_from_schema(req_name, req_schema, req_exec_script_root_dir = "${WORK_DIR}"):
    req_type = req_schema["Method"]
    req_api = req_schema["Query"]
    req_params = req_schema["Params"]

    content_type=""
    if "Content-Type" in req_schema:
        content_type = req_schema["Content-Type"]

    parallel_by_session = req_schema.get("ParallelBySession", False)
    if not isinstance(parallel_by_session, bool):
        raise ValueError("ParallelBySession must be a boolean")

    return generate_cli_server_content(
        req_name,
        req_api,
        req_type,
        content_type,
        req_exec_script_root_dir,
        parallel_by_session,
    )


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
        cli_server_content = create_cli_server_content_from_schema(req_name, request_data, executor_generated_scripts_path)
        api_server_script_file_path = get_api_cli_service_script_path(generated_api_server_scripts_path, req_name)
        with open(api_server_script_file_path, "w") as server_file:
            server_file.write("#!/bin/bash\n\n")
            server_file.writelines(cli_server_content)
        filesystem_utils.make_file_executable(api_server_script_file_path)


        # generate GUI API listener
        gui_server_content = create_gui_server_content_from_schema(req_name, request_data, executor_generated_scripts_path)
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
