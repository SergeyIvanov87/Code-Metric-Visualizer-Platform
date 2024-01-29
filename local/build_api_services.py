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

import filesystem_utils

from api_gen_utils import compose_api_fs_node_name
from api_gen_utils import compose_api_exec_script_name
from api_gen_utils import compose_api_help_script_name
from api_gen_utils import get_api_cli_service_script_path
from api_gen_utils import get_api_schema_files
from api_gen_utils import decode_api_request_from_schema_file
from api_gen_utils import get_api_gui_service_script_path
from api_gen_utils import get_generated_scripts_path
from api_gen_utils import get_api_leaf_node_name
from api_gen_utils import file_extension_from_content_type

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

parser.add_argument("api_root_dir", help="Path to the root directory incorporated JSON API schema descriptions")
parser.add_argument("generated_exec_script_dir", help="Path to the directory where the api executable scripts were generated")
parser.add_argument("-o", "--output_dir",
                    help='Output directory where the generated scripts will be placed. Default=\"./{}\"'.format(get_generated_scripts_path()),
                    default=get_generated_scripts_path())

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
    "\t\t\tACCESS|ATTRIB|MODIFY )\n",
    "\t\t\t\tdate=`date +%Y-%m-%dT%H:%M:%S`\n",
    "\t\t\t\ttouch {0}/in_progress\n",
    '\t\t\t\t"${0}/{1}" ${2} {3} 0 > {4}${5}\n',
    '\t\t\t\tchmod +rw {0}${1}\n',
    "\t\t\t\trm -f {0}/in_progress\n",
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
    "if [[ -p $pipe_result ]]; then\n",
    "\trm -f $pipe_result\n",
    "fi\n",
    "mkfifo -m 622 $pipe_request\n",
    'trap "rm -f $pipe_request" ${SIGNALS}\n',
    "mkfifo -m 644 $pipe_result\n",
    'trap "rm -f $pipe_result" ${SIGNALS}\n',
    'WATCH_PID=0\n',
    "while true\n",
    "do\n",
    '\tif [[ -f "${api_req_node}/in_progress" ]]; then\n',
    '\t\trm -f "${api_req_node}/in_progress"\n',
    "\tfi\n",
    "\tCMD_READ=`cat $pipe_request`\n",
    '\t echo "START: ${api_req_node}"\n',
    "\tif [ ${WATCH_PID} != 0 ]; then\n",
    "\t\t# check WATCHDOG alive\n",
    "\t\tkill -s 0 ${WATCH_PID} > /dev/null 2>&1\n",
    "\t\tWATCHDOG_RESULT=$?\n",
    "\t\tif [ $WATCHDOG_RESULT == 0 ]; then\n",
    "\t\t\t# its alive: nobody has read $pipe_result yet. Initiate reading intentionally\n",
    "\t\t\ttimeout 2 cat ${pipe_result} > /dev/null 2>&1\n",
    "\t\tfi\n",
    "\t\t# avoid zombie\n",
    "\t\twait ${WATCH_PID}\n",
    "\tfi\n",
    '\ttouch "${api_req_node}/in_progress"\n',
    '\tRESULT_OUT=$(${0}/{1} ${2} {3} ', '"${CMD_READ}" | base64)\n',
    '\trm -f ${api_req_node}/in_progress\n',
    '\t(touch ${api_req_node}/ready && echo "${RESULT_OUT}" | base64 -d >$pipe_result && rm -rf ${api_req_node}/ready && echo "CONSUMED: ${api_req_node}") &\n',
    "\tWATCH_PID=$!\n",
    '\ttrap "rm -f $pipe_request" ${SIGNALS} # as resets after subshell invocation\n',
    '\ttrap "rm -f $pipe_result" ${SIGNALS} # as resets after subshell invocation\n',
    "done\n",
]

generated_api_server_scripts_path = args.output_dir
os.makedirs(generated_api_server_scripts_path, exist_ok=True)

schemas_file_list = get_api_schema_files(args.api_root_dir)
errors_detected = []
for schema_file in schemas_file_list:
    req_name, request_data = decode_api_request_from_schema_file(schema_file)
    req_type = request_data["Method"]
    req_api = request_data["Query"]
    req_params = request_data["Params"]

    content_type=""
    if "Content-Type" in request_data:
        content_type = request_data["Content-Type"]

    api_node, api_req_node = compose_api_fs_node_name(
            "${INITIAL_PROJECT_LOCATION}", req_api, req_type
    )

    try:
        req_executor_name = check_script_valid(args.generated_exec_script_dir, req_name)
    except Exception as e:
        errors_detected.append(str(e))
        continue

    # generate GUI API listener
    api_server_script_file_path = get_api_gui_service_script_path(generated_api_server_scripts_path, req_name)
    with open(api_server_script_file_path, "w") as listener_file:
        api_gui_schema_concrete = api_gui_schema.copy()
        api_gui_schema_concrete[1] = api_gui_schema_concrete[1].format(
            "${WORK_DIR}/" + compose_api_help_script_name(req_name), api_node
        )

        # determine result type: either from JSON or from script renerated
        if len(content_type) != 0:
            api_gui_schema_concrete[3] = "EXT=." + file_extension_from_content_type(content_type) + "\n"
        else:
            api_gui_schema_concrete[3] = api_gui_schema_concrete[3].format("{WORK_DIR}",req_executor_name)

        api_gui_schema_concrete[4] = api_gui_schema_concrete[4].format(
            api_req_node, get_fs_watch_event_for_request_type(req_type), get_api_leaf_node_name(req_type) + "$"
        )
        api_gui_schema_concrete[10] = api_gui_schema_concrete[10].format(
            api_req_node)

        api_gui_schema_concrete[11] = api_gui_schema_concrete[11].format(
            "{WORK_DIR}",
            req_executor_name,
            "{MAIN_IMAGE_ENV_SHARED_LOCATION}",
            api_node,
            os.path.join(api_req_node, "result_${date}"),
            "{EXT}"
        )

        api_gui_schema_concrete[12] = api_gui_schema_concrete[12].format(
            os.path.join(api_req_node, "result_${date}"),
            "{EXT}"
        )
        api_gui_schema_concrete[13] = api_gui_schema_concrete[13].format(
            api_req_node)

        listener_file.write("#!/usr/bin/bash\n\n")
        listener_file.writelines(api_gui_schema_concrete)

    filesystem_utils.make_file_executable(api_server_script_file_path)

    #generate CLI API server
    api_server_script_file_path = get_api_cli_service_script_path(generated_api_server_scripts_path, req_name)
    with open(api_server_script_file_path, "w") as server_file:
        api_cli_schema_concrete = api_cli_schema.copy()
        api_cli_schema_concrete[1] = api_cli_schema_concrete[1].format(api_req_node
        )

        # determine result type: either from JSON or from script renerated
        if len(content_type) != 0:
            api_cli_schema_concrete[3] = "EXT=." + file_extension_from_content_type(content_type) + "\n"
        else:
            api_cli_schema_concrete[3] = api_cli_schema_concrete[3].format("{WORK_DIR}",req_executor_name)

        api_cli_schema_concrete[37] = api_cli_schema_concrete[37].format(
            "{WORK_DIR}",
            req_executor_name,
            "{MAIN_IMAGE_ENV_SHARED_LOCATION}",
            api_node
        )

        server_file.write("#!/usr/bin/bash\n\n")
        server_file.writelines(api_cli_schema_concrete)

    filesystem_utils.make_file_executable(api_server_script_file_path)

if len(errors_detected) != 0:
    raise Exception(
        "Erros detected:\n{}\nScript execdir: {}".format(
            "\n".join(errors_detected), pathlib.Path(__file__).parent.resolve()
        )
    )
