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

from api_gen_utils import compose_api_fs_node_name
from api_gen_utils import compose_api_exec_script_name
from api_gen_utils import compose_api_help_script_name
from api_gen_utils import get_api_cli_service_script_path
from api_gen_utils import get_api_gui_service_script_path
from api_gen_utils import get_generated_scripts_path
from api_gen_utils import make_file_executable
from api_gen_utils import append_file_mode
from api_gen_utils import get_api_hidden_node_name

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


parser = argparse.ArgumentParser(
    prog="Build file-system API nodes based on pseudo-REST API from cfg file"
)

parser.add_argument("api_file", help="Path to file with API description")

args = parser.parse_args()

api_gui_schema = [
    ". ${1}/setenv.sh\n",
    "{} > {}/help 2>&1\n",
    "shopt -s extglob\n",
    "EXT=`${0}/{1} --result_type`\n",
    "inotifywait -m {0} -e {1} --include '{2}' |\n",
    "\twhile read dir action file; do\n",
    '\t\techo "file: ${file}, action; ${action}, dir: ${dir}"\n',
    '\t\tcase "$action" in\n',
    "\t\t\tACCESS|ATTRIB )\n",
    "\t\t\t\tdate=`date +%Y-%m-%dT%H:%M:%S`\n",
    '\t\t\t\t"${0}/{1}" ${2} {3} > {4}${5}\n',
    '\t\t\t\tchmod +rw {0}${1}\n',
    "\t\t\t;;\n",
    "\t\t\t*)\n",
    "\t\t\t\t;;\n",
    "\t\tesac\n",
    "\tdone\n",
]

api_cli_schema = [
    ". ${1}/setenv.sh\n",
    "api_req_node={}\n",
    "shopt -s extglob\n",
    "EXT=`${0}/{1} --result_type`\n",
    "pipe_result=${api_req_node}/result${EXT}\n",
    "pipe_request=${api_req_node}/exec\n",
    'SIGNALS="HUP QUIT ABRT KILL EXIT TERM"\n',
    "if [[ -p $pipe_request ]]; then\n",
    "\trm -f $pipe_request\n",
    "fi\n",
    "mkfifo $pipe_request\n",
    'trap "rm -f $pipe_request" ${SIGNALS}\n',
    "while true\n",
    "do\n",
    "\techo 0 >$pipe_request\n",
    '\tRESULT_OUT=`${0}/{1} ${2} {3}`\n',
    "\tif [[ -p $pipe_result ]]; then\n",
    "\t\trm -f $pipe_result\n",
    "\tfi\n",
    "\tmkfifo $pipe_result\n",
    '\ttrap "rm -f $pipe_result" ${SIGNALS}\n',
    "\t(echo ${RESULT_OUT}>$pipe_result && rm -f $pipe_result) > /dev/null 2>&1 &\n",
    'trap "rm -f $pipe_request" ${SIGNALS} # as resets after subshell invocation\n',
    "done\n",
]

os.makedirs(get_generated_scripts_path(), exist_ok=True)

errors_detected = []
with open(args.api_file, "r") as api_file:
    for request_line in api_file:
        request_params = [s.strip() for s in request_line.split("\t")]
        if len(request_params) < 3:
            continue

        (req_name, req_type, req_api, *req_params) = request_params
        api_node, api_req_node = compose_api_fs_node_name(
                "${INITIAL_PROJECT_LOCATION}", req_api, req_type
            )

        try:
            req_executor_name = check_script_valid("", req_name)
        except Exception as e:
            errors_detected.append(str(e))
            continue

        # generate GUI API listener
        api_server_script_file_path = get_api_gui_service_script_path(req_name)
        with open(api_server_script_file_path, "w") as listener_file:
            api_gui_schema_concrete = api_gui_schema.copy()
            api_gui_schema_concrete[1] = api_gui_schema_concrete[1].format(
                "${WORK_DIR}/" + compose_api_help_script_name(req_name), api_node
            )
            api_gui_schema_concrete[3] = api_gui_schema_concrete[3].format("{WORK_DIR}",req_executor_name)
            api_gui_schema_concrete[4] = api_gui_schema_concrete[4].format(
                api_req_node, get_fs_watch_event_for_request_type(req_type), get_api_hidden_node_name() + "$"
            )
            api_gui_schema_concrete[10] = api_gui_schema_concrete[10].format(
                "{WORK_DIR}",
                req_executor_name,
                "{MAIN_IMAGE_ENV_SHARED_LOCATION}",
                api_node,
                os.path.join(api_req_node, "result_${date}"),
                "{EXT}"
            )

            api_gui_schema_concrete[11] = api_gui_schema_concrete[11].format(
                os.path.join(api_req_node, "result_${date}"),
                "{EXT}"
            )
            listener_file.write("#!/usr/bin/bash\n\n")
            listener_file.writelines(api_gui_schema_concrete)

        make_file_executable(api_server_script_file_path)

        #generate CLI API server
        api_server_script_file_path = get_api_cli_service_script_path(req_name)
        with open(api_server_script_file_path, "w") as server_file:
            api_cli_schema_concrete = api_cli_schema.copy()
            api_cli_schema_concrete[1] = api_cli_schema_concrete[1].format(api_req_node
            )
            api_cli_schema_concrete[3] = api_cli_schema_concrete[3].format("{WORK_DIR}",req_executor_name)

            api_cli_schema_concrete[15] = api_cli_schema_concrete[15].format(
                "{WORK_DIR}",
                req_executor_name,
                "{MAIN_IMAGE_ENV_SHARED_LOCATION}",
                api_node
            )

            server_file.write("#!/usr/bin/bash\n\n")
            server_file.writelines(api_cli_schema_concrete)

        make_file_executable(api_server_script_file_path)

if len(errors_detected) != 0:
    raise Exception(
        "Erros detected:\n{}\nScript execdir: {}".format(
            "\n".join(errors_detected), pathlib.Path(__file__).parent.resolve()
        )
    )
