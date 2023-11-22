#!/usr/bin/python

import argparse
import os
import pathlib
import sys
import stat


EXEC_MODE = ["devel", "build", "run"]
EXEC_MODE_DEV=0
EXEC_MODE_HOST=1
EXEC_MODE_IMAGE=2

def append_file_mode(file, append_modes):
    st = os.stat(file)
    os.chmod(file, st.st_mode | append_modes)

def make_file_executable(file):
    append_file_mode(file, stat.S_IEXEC)

def compose_api_fs_node_name(api_root, req):
    api_node = os.path.join(api_root, req)
    return api_node

def create_api_fs_node(api_root, req, req_type, req_params):
    api_node = compose_api_fs_node_name(api_root, req)
    os.makedirs(api_node, exist_ok=True);
    api_node_leaf = os.path.join(api_node, req_type)

    with open(api_node_leaf, "w") as api_leaf_file:
        if req_type == "GET":
            make_file_executable(api_node_leaf)
        else:
            append_file_mode(api_node_leaf, stat.S_IWUSR | stat.S_IRUSR | stat.S_IWGRP | stat.S_IRGRP | stat.S_IWOTH | stat.S_IROTH)

        api_leaf_file.write("0\n")    # event `access` in notify can't be trigger on empty file

    #create params as files
    counter = 0
    for param in req_params:
        param_name, param_value = param.split("=")
        param_name_path = os.path.join(api_node,str(counter) + "." + param_name)
        counter += 1

        with open(param_name_path, "w") as api_file_param:
            api_file_param.write(param_value)
            append_file_mode(param_name_path, stat.S_IWUSR | stat.S_IRUSR | stat.S_IWGRP | stat.S_IRGRP | stat.S_IWOTH | stat.S_IROTH)

    return api_node

def compose_script_for_dev_name(script_name):
    return f"{script_name}_exec.sh"

EMPTY_DEV_SCRIPT_MARK="<TODO: THE SCRIPT IS EMPTY>"
def make_script_generate_xml(script):
    script.write("#!/usr/bin/bash\n\n. $1/setenv.sh\n\nRESULT_FILE=${2}_result\n\n")
    script.write("find ${REPO_PATH} -regex \".*\.\(hpp\|cpp\|c\|h\)\" | grep -v \"buil\" | grep -v \"3pp\" | grep -v \"thirdpart\" | ${WORK_DIR}/pmccabe_visualizer/pmccabe_build.py > ${SHARED_API_DIR}/${RESULT_FILE}.xml")

def make_script_generate_fgraph(script):
    script.write("#!/usr/bin/bash\n\n. $1/setenv.sh\n\n")
    script.write("RESULT_FILE=${2}_result\n\n")
    script_name_generated = compose_script_for_dev_name("generate_xml")
    script.write("${WORK_DIR}/" + script_name_generated +  " ${1} ${2}\n")
    script.write("cat ${SHARED_API_DIR}/${RESULT_FILE}.xml | ${WORK_DIR}/pmccabe_visualizer/collapse.py mmcc,tmcc,sif,lif | ${WORK_DIR}/FlameGraph/flamegraph.pl > ${SHARED_API_DIR}/${RESULT_FILE}.svg\n")

def make_default_script(script):
    script.write(f"#!/usr/bin/bash\n\n. ${1}/setenv.sh\n\nRESULT_FILE=${2}_result\n\n{EMPTY_DEV_SCRIPT_MARK}")


def make_script_watch_list(script):
    body =(r'#!/usr/bin/bash',
           r'',
           r'API_NODE=${1}',
           r'. $2/setenv.sh',
           r'RESULT_FILE=${3}_result',
           r'CMD_ARGS=""',
           r'for entry in "${API_NODE}"/*.*',
           r'do',
           r'    file_basename=${entry##*/}',
           r'    param_name=${file_basename#*.}',
           r'    readarray -t arr < ${entry}',
           r'    brr+=(${param_name})',
           r'    for a in ${arr[@]}',
           r'    do',
           r'        if [[ ${a} == \"* ]];',
           r'        then',
           r'            brr+=("${a}")',
           r'        else',
           r'            brr+=(${a})',
           r'        fi',
           r'    done',
           r'done',
           r'echo "${brr[@]}" | xargs find ${REPO_PATH} > ${RESULT_FILE}.txt'
          )
    script.writelines(line + '\n' for line in body)

def make_script_statistic(script):
    body =(r'#!/usr/bin/bash',
           r'',
           r'API_NODE=${1}',
           r'. $2/setenv.sh',
           r'RESULT_FILE=${3}_result',
           r'CMD_ARGS=""',
           r'for entry in "${API_NODE}"/*.*',
           r'do',
           r'    file_basename=${entry##*/}',
           r'    param_name=${file_basename#*.}',
           r'    readarray -t arr < ${entry}',
           r'    brr+=(${param_name})',
           r'    for a in ${arr[@]}',
           r'    do',
           r'        if [[ ${a} == \"* ]];',
           r'        then',
           r'            brr+=("${a}")',
           r'        else',
           r'            brr+=(${a})',
           r'        fi',
           r'    done',
           r'done',
           r'echo "${brr[@]}"'
          )
    script.writelines(line + '\n' for line in body)

def make_script_view(script):
    body =(r'#!/usr/bin/bash',
           r'',
           r'API_NODE=${1}',
           r'. $2/setenv.sh',
           r'RESULT_FILE=${3}_result',
           r'CMD_ARGS=""',
           r'for entry in "${API_NODE}"/*.*',
           r'do',
           r'    file_basename=${entry##*/}',
           r'    param_name=${file_basename#*.}',
           r'    readarray -t arr < ${entry}',
           r'    brr+=(${param_name})',
           r'    for a in ${arr[@]}',
           r'    do',
           r'        if [[ ${a} == \"* ]];',
           r'        then',
           r'            brr+=("${a}")',
           r'        else',
           r'            brr+=(${a})',
           r'        fi',
           r'    done',
           r'done',
           r'${WORK_DIR}/watch_list_exec.sh ${SHARED_API_DIR}/project/{uuid} ${WORK_DIR} ${API_NODE}/.watch_list',
           r'cat ${API_NODE}/.watch_list_result.txt | ${WORK_DIR}/pmccabe_visualizer/pmccabe_build.py `${WORK_DIR}/statistic_exec.sh ${SHARED_API_DIR}/project/{uuid}/statistic ${WORK_DIR} stst` > ${RESULT_FILE}.xml',
           r'cat ${RESULT_FILE}.xml | ${WORK_DIR}/pmccabe_visualizer/collapse.py ${brr[@]} > ${RESULT_FILE}.data',
          )
    script.writelines(line + '\n' for line in body)

def make_script_flamegraph(script):
    body =(r'#!/usr/bin/bash',
           r'',
           r'API_NODE=${1}',
           r'. $2/setenv.sh',
           r'RESULT_FILE=${3}_result',
           r'CMD_ARGS=""',
           r'for entry in "${API_NODE}"/*.*',
           r'do',
           r'    file_basename=${entry##*/}',
           r'    param_name=${file_basename#*.}',
           r'    readarray -t arr < ${entry}',
           r'    brr+=(${param_name})',
           r'    for a in ${arr[@]}',
           r'    do',
           r'        if [[ ${a} == \"* ]];',
           r'        then',
           r'            brr+=("${a}")',
           r'        else',
           r'            brr+=(${a})',
           r'        fi',
           r'    done',
           r'done',
           r'${WORK_DIR}/view_exec.sh ${SHARED_API_DIR}/project/{uuid}/statistic/view ${WORK_DIR} ${API_NODE}/.collapsed',
           r'cat ${API_NODE}/.collapsed_result.data | ${WORK_DIR}/FlameGraph/flamegraph.pl ${brr[@]} > ${RESULT_FILE}.svg',
          )
    script.writelines(line + '\n' for line in body)


scripts_generator = {"watch_list": make_script_watch_list,
                     "statistic" : make_script_statistic,
                     "view" : make_script_view,
                     "flamegraph" : make_script_flamegraph,
                     "generate_fgraph" : make_script_generate_fgraph}

def create_script_for_dev(path, script_name):
    script_name_generated = compose_script_for_dev_name(script_name)
    script_generated_path = os.path.join(path, script_name_generated)

    with open(script_generated_path, "x") as script:
        make_file_executable(script_generated_path)
        if script_name in scripts_generator.keys():
            scripts_generator[script_name](script)
        else:
            make_default_script(script)

    return script_name_generated

def check_script_valid(path, script_name):
    script_name_generated = compose_script_for_dev_name(script_name)
    script_generated_path = os.path.join(path, script_name_generated)

    with open(script_generated_path, "r") as script:
        for l in script:
            if l == EMPTY_DEV_SCRIPT_MARK:
                raise NotImplementedError(f"Script \"{script_name_generated}\" must be implemented, path: {script_generated_path}")

    return script_name_generated

def get_fs_watch_event_for_request_type(req_type):
    events = {"GET": "-e access", "PUT" : "-e modify"}
    if req_type not in events.keys():
        raise Exception(f"Request type is not supported: {req_type}. Available types are: {events.keys()}")
    return events[req_type]

parser = argparse.ArgumentParser(
    prog="Build file-system API nodes based on pseudo-REST API from cfg file"
)

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
    raise Exception('Invalid execution mode: {}. Supported values: {}'.format(args.mode, EXEC_MODE))

api_schema = [". ${1}/setenv.sh\n",
"shopt -s extglob\n",
"inotifywait -m {0} {1} --include '{2}' |\n",
"\twhile read dir action file; do\n",
"\t\techo \"file: ${file}, action; ${action}, dir: ${dir}\"\n",
"\t\tcase \"$action\" in\n",
"\t\t\tACCESS|ATTRIB )\n",
"\t\t\t\t\"${0}/{1}\" {2} ${3} ${4}\n",
"\t\t\t;;\n",
"\t\t\t*)\n",
"\t\t\t\t;;\n",
"\t\tesac\n",
"\tdone\n"
]

generated_api_server_scripts_path = "services"
os.makedirs(generated_api_server_scripts_path, exist_ok=True);

errors_detected=[]
with open(args.api_file, 'r') as api_file:
     for request_line in api_file:
            request_params = [s.strip() for s in request_line.split('\t')];
            if len(request_params) < 3:
                continue

            (req_name, req_type, req_api, *req_params) = request_params
            '''re-create filesystem directory structure based on API query'''
            '''must be done in 'run' mode only'''
            if args.mode == EXEC_MODE[EXEC_MODE_IMAGE]:
                api_node = create_api_fs_node(args.mount_point, req_api, req_type, req_params)
                continue
            else:
                api_node = compose_api_fs_node_name(args.mount_point, req_api)

            '''in 'devel' mode this builder must generate stub files for API request to implement'''
            '''must be done BEFORE docker image crafted'''
            if args.mode == EXEC_MODE[EXEC_MODE_DEV]:
                try:
                    req_executor_name = create_script_for_dev(generated_api_server_scripts_path, req_name)
                except FileExistsError as e:
                    print(f"Skipping the script \"{req_name}\" creation in \"{EXEC_MODE[EXEC_MODE_DEV]}\":\n\t\"{e}\"")
                    continue
                except Exception as e:
                    errors_detected.append(str(e))
                    continue
            else:
                try:
                    req_executor_name = check_script_valid("", req_name)
                except Exception as e:
                    errors_detected.append(str(e))
                    continue

            '''must not generate served listeners scripts in 'run' mode'''
            api_server_script_file_name = f"{req_name}_listener.sh"
            api_server_script_file_path = os.path.join(generated_api_server_scripts_path, api_server_script_file_name)

            '''In dev mode generate it in testing purposes'''
            if args.mode == EXEC_MODE[EXEC_MODE_DEV]:
                api_server_script_file_path += ".test_only"

            with open(api_server_script_file_path, "w") as listener_file:
                api_schema_concrete = api_schema.copy()
                api_schema_concrete[2] = api_schema_concrete[2].format(api_node, get_fs_watch_event_for_request_type(req_type), req_type)
                api_schema_concrete[7] = api_schema_concrete[7].format("{WORK_DIR}", req_executor_name, api_node, "{WORK_DIR}", "{API_NODE}/${file}")

                listener_file.write("#!/usr/bin/bash\n\n")
                listener_file.writelines(api_schema_concrete)

            make_file_executable(api_server_script_file_path)

if len(errors_detected) != 0:
    raise Exception("Erros detected:\n{}\nScript execdir: {}".format('\n'.join(errors_detected), pathlib.Path(__file__).parent.resolve()))
