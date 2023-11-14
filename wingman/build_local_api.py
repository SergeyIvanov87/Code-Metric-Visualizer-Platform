#!/usr/bin/python

import argparse
import os
import sys
import stat

def make_file_executable(file):
    st = os.stat(file)
    os.chmod(file, st.st_mode | stat.S_IEXEC)

parser = argparse.ArgumentParser(
    prog="Build file-system API nodes based on pseudo-REST API from cfg file"
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

api_schema = ["inotifywait -m {0} -e access --include 'get' |\n",
"\twhile read dir action file; do\n",
"\t\techo \"file: ${file}, action; ${action}, dir: ${dir}\"\n",
"\t\tcase \"$action\" in\n",
"\t\t\tACCESS|ATTRIB )\n",
"\t\t\t\t\"${WORK_DIR}/",
"<generate>",
"\t\t\t;;\n",
"\t\t\t*)\n",
"\t\t\t\t;;\n",
"\t\tesac\n",
"\tdone\n"
]

generated_api_server_scripts_path = "generated"
os.makedirs(generated_api_server_scripts_path, exist_ok=True);

with open(args.api_file, 'r') as api_file:
     for request_line in api_file:
            request_params = request_line.split();
            if len(request_params) != 3:
                continue

            (req_name, req_type, req_api) = request_params

            '''re-create filesystem directory structure based on API query'''
            api_node = os.path.join(args.mount_point, req_api)
            os.makedirs(api_node, exist_ok=True);
            api_node_leaf = os.path.join(api_node, req_type.lower())

            with open(api_node_leaf, "w") as api_leaf_file:
                make_file_executable(api_node_leaf)
                api_leaf_file.write("0\n")    # event `access` in notify can't be trigger on empty file

                api_server_script_file_name = f"{req_name}_listener.sh"
                api_server_script_file_path = os.path.join(generated_api_server_scripts_path, api_server_script_file_name)
                with open(api_server_script_file_path, "w") as listener_file:
                    api_schema_concrete = api_schema.copy()
                    api_schema_concrete[0] = api_schema_concrete[0].format(api_node)
                    api_schema_concrete[6] = f"{req_name}_exec.sh\"\n"

                    listener_file.write("#!/usr/bin/bash\n\n")
                    listener_file.writelines(api_schema_concrete)

                    make_file_executable(api_server_script_file_path)
