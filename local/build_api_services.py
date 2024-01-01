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
from api_gen_utils import get_api_service_script_path
from api_gen_utils import get_generated_scripts_path
from api_gen_utils import make_file_executable
from api_gen_utils import append_file_mode

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
    events = {"GET": "-e access", "PUT": "-e modify", "POST": "-e modify"}
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

api_schema = [
    ". ${1}/setenv.sh\n",
    "{} > {}/help 2>&1\n",
    "shopt -s extglob\n",
    "inotifywait -m {0} {1} --include '{2}' |\n",
    "\twhile read dir action file; do\n",
    '\t\techo "file: ${file}, action; ${action}, dir: ${dir}"\n',
    '\t\tcase "$action" in\n',
    "\t\t\tACCESS|ATTRIB )\n",
    '\t\t\t\t"${0}/{1}" ${2} {3} {4}/{5}\n',
    "\t\t\t;;\n",
    "\t\t\t*)\n",
    "\t\t\t\t;;\n",
    "\t\tesac\n",
    "\tdone\n",
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

        api_server_script_file_path = get_api_service_script_path(req_name)
        with open(api_server_script_file_path, "w") as listener_file:
            api_schema_concrete = api_schema.copy()
            api_schema_concrete[1] = api_schema_concrete[1].format(
                "${WORK_DIR}/" + compose_api_help_script_name(req_name), api_node
            )
            api_schema_concrete[3] = api_schema_concrete[3].format(
                api_req_node, get_fs_watch_event_for_request_type(req_type), "exec$"
            )
            api_schema_concrete[8] = api_schema_concrete[8].format(
                "{WORK_DIR}",
                req_executor_name,
                "{MAIN_IMAGE_ENV_SHARED_LOCATION}",
                api_node,
                api_req_node,
                "${file}",
            )
            listener_file.write("#!/usr/bin/bash\n\n")
            listener_file.writelines(api_schema_concrete)

        make_file_executable(api_server_script_file_path)

if len(errors_detected) != 0:
    raise Exception(
        "Erros detected:\n{}\nScript execdir: {}".format(
            "\n".join(errors_detected), pathlib.Path(__file__).parent.resolve()
        )
    )
