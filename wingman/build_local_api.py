#!/usr/bin/python

import argparse
import os
import sys
import stat

def make_file_executable(file):
    st = os.stat(file)
    os.chmod(file, st.st_mode | stat.S_IEXEC)

def compose_api_fs_node_name(api_root, req):
    api_node = os.path.join(api_root, req)
    return api_node

def create_api_fs_node(api_root, req, req_type):
    api_node = compose_api_fs_node_name(api_root, req)
    os.makedirs(api_node, exist_ok=True);
    api_node_leaf = os.path.join(api_node, req_type.lower())

    with open(api_node_leaf, "w") as api_leaf_file:
        make_file_executable(api_node_leaf)
        api_leaf_file.write("0\n")    # event `access` in notify can't be trigger on empty file
    return api_node

def compose_script_for_dev_name(script_name):
    return f"{script_name}_exec.sh"

def create_script_for_dev(path, script_name):
    script_name_generated = compose_script_for_dev_name(script_name)
    script_generated_path = os.path.join(path, script_name_generated)
    with open(script_generated_path, "w") as script:
        make_file_executable(script_generated_path)
        script.write("#!/usr/bin/bash\n\n. ${1}/setenv.sh\n<TODO>")

    return script_name_generated

parser = argparse.ArgumentParser(
    prog="Build file-system API nodes based on pseudo-REST API from cfg file"
)

EXEC_MODE = ["devel", "build", "run"]
EXEC_MODE_DEV=0
EXEC_MODE_HOST=1
EXEC_MODE_IMAGE=2

parser.add_argument(
    "mode",
    help=f"Script execution mode: {EXEC_MODE}"
)

parser.add_argument(
    "api_file",
    help="Path to file with API description"
)

parser.add_argument(
    "mount_point",
    help="destination to build file-system nodes"
)


args = parser.parse_args()
if args.mode not in EXEC_MODE:
    raise Exception("Invalid execution mode: {}. Supported values: {}".format(args.mode, EXEC_MODE))

api_schema = [". ${1}/setenv.sh\n",
"shopt -s extglob\n",
"inotifywait -m {0} -e access --include 'get' |\n",
"\twhile read dir action file; do\n",
"\t\techo \"file: ${file}, action; ${action}, dir: ${dir}\"\n",
"\t\tcase \"$action\" in\n",
"\t\t\tACCESS|ATTRIB )\n",
"\t\t\t\t\"${0}/{1}\" ${2}\n",
"\t\t\t;;\n",
"\t\t\t*)\n",
"\t\t\t\t;;\n",
"\t\tesac\n",
"\tdone\n"
]

generated_api_server_scripts_path = "services"
os.makedirs(generated_api_server_scripts_path, exist_ok=True);

with open(args.api_file, 'r') as api_file:
     for request_line in api_file:
            request_params = request_line.split();
            if len(request_params) != 3:
                continue

            (req_name, req_type, req_api) = request_params

            '''re-create filesystem directory structure based on API query'''
            '''must be done in 'run' mode only'''
            if args.mode == EXEC_MODE[EXEC_MODE_IMAGE]:
                api_node = create_api_fs_node(args.mount_point, req_api, req_type)
                continue
            else:
                api_node = compose_api_fs_node_name(args.mount_point, req_api)

            '''in 'devel' mode this builder must generate stub files for API request to implement'''
            '''must be done BEFORE docker image crafted'''
            if args.mode == EXEC_MODE[EXEC_MODE_DEV]:
                req_executor_name = create_script_for_dev(generated_api_server_scripts_path, req_name)
            else:
                req_executor_name = compose_script_for_dev_name(req_name)


            '''must not generate served listeners scripts in 'run' mode'''
            api_server_script_file_name = f"{req_name}_listener.sh"
            api_server_script_file_path = os.path.join(generated_api_server_scripts_path, api_server_script_file_name)

            '''In dev mode generate it in testing purposes'''
            if args.mode == EXEC_MODE[EXEC_MODE_DEV]:
                api_server_script_file_path += ".test_only"

            with open(api_server_script_file_path, "w") as listener_file:
                api_schema_concrete = api_schema.copy()
                api_schema_concrete[2] = api_schema_concrete[2].format(api_node)
                api_schema_concrete[7] = api_schema_concrete[7].format("{WORK_DIR}", req_executor_name, "{WORK_DIR}")

                listener_file.write("#!/usr/bin/bash\n\n")
                listener_file.writelines(api_schema_concrete)

            make_file_executable(api_server_script_file_path)
