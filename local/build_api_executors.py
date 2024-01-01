#!/usr/bin/python

"""
Generates `executor` script for API request serving
"""

import argparse
from math import log10
import os
import pathlib
import sys
import stat

from api_gen_utils import compose_api_exec_script_name
from api_gen_utils import compose_api_fs_node_name
from api_gen_utils import get_generated_scripts_path
from api_gen_utils import make_file_executable
from api_gen_utils import append_file_mode

EMPTY_DEV_SCRIPT_MARK = "<TODO: THE SCRIPT IS EMPTY>"

def make_default_script(script):
    script.write(
        f"#!/usr/bin/bash\n\n. ${1}/setenv.sh\n\nRESULT_FILE=${2}_result\n\n{EMPTY_DEV_SCRIPT_MARK}"
    )

parser = argparse.ArgumentParser(
    prog="Build file-system API nodes based on pseudo-REST API from cfg file"
)

parser.add_argument("api_file", help="Path to a file with API description")
parser.add_argument("api_exec_generator", help="Path to a file with API generators")
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
    '\t\t\t\t"${0}/{1}" {2} ${3} {4}/{5}\n',
    "\t\t\t;;\n",
    "\t\t\t*)\n",
    "\t\t\t\t;;\n",
    "\t\tesac\n",
    "\tdone\n",
]

# Load api generator module
sys.path.append(args.api_exec_generator)
import api_generator
scripts_generator, _ = api_generator.get()

generated_api_server_scripts_path = get_generated_scripts_path()
os.makedirs(generated_api_server_scripts_path, exist_ok=True)

errors_detected = []
with open(args.api_file, "r") as api_file:
    for request_line in api_file:
        request_params = [s.strip() for s in request_line.split("\t")]
        if len(request_params) < 3:
            continue

        req_name = request_params[0]

        """this builder must generate stub files for API request to implement"""
        """Must be done BEFORE docker image crafted"""
        try:
            script_name_generated = compose_api_exec_script_name(req_name)
            script_generated_path = os.path.join(generated_api_server_scripts_path, script_name_generated)

            with open(script_generated_path, "x") as script:
                make_file_executable(script_generated_path)
                if req_name in scripts_generator.keys():
                    scripts_generator[req_name](script)
                else:
                    make_default_script(script)
        except FileExistsError as e:
            print(
                f'Skipping the script "{req_name}":\n\t"{e}"'
            )
            continue
        except Exception as e:
            errors_detected.append(str(e))
            continue

if len(errors_detected) != 0:
    raise Exception(
        "Erros detected:\n{}\nScript execdir: {}".format(
            "\n".join(errors_detected), pathlib.Path(__file__).parent.resolve()
        )
    )
