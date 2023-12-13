#!/usr/bin/python

"""
Although this module has many purposes, the one goal of generating a container
interface is united them. The interface carry on similar ideas as
the `proc` pseudo-filesystem emboding. Having read the API IDL file produced by
`build_api.py`, it generates pseudo-filesystem API gradually operating in
different modes:

- `run`
For each API query is creates as file-system hierarchy (API_NODE) which
terminated by a leaf file called `exec`.
Triggering an appropriate operation on that interface file, for example simple
`access` for GET-query or `write` for PUT-query, will execute the initial API query

- `devel`
For each API query if produces a `listener` and an `executor` scripts both.
The `listener` awaits appropriate events on API_NODE and the `executor` carry out
the logic serving API-query

- `build`
Just unpacks scripts and pseudo-filesystem in docker image space
"""

import argparse
from math import log10
import os
import pathlib
import sys
import stat


EXEC_MODE = ["devel", "build", "run"]
EXEC_MODE_DEV = 0
EXEC_MODE_HOST = 1
EXEC_MODE_IMAGE = 2


def append_file_mode(file, append_modes):
    st = os.stat(file)
    os.chmod(file, st.st_mode | append_modes)


def make_file_executable(file):
    append_file_mode(file, stat.S_IEXEC)


def compose_api_fs_node_name(api_root, req, rtype):
    anode = os.path.join(api_root, req)
    areq_node = os.path.join(anode, rtype)
    return anode, areq_node


def create_api_fs_node(api_root, req, rtype, rparams):
    api_node, api_req_node = compose_api_fs_node_name(api_root, req, rtype)
    os.makedirs(api_req_node, exist_ok=True)
    api_node_leaf = os.path.join(api_req_node, "exec")

    with open(api_node_leaf, "w") as api_leaf_file:
        if rtype == "GET":
            make_file_executable(api_node_leaf)
        else:
            append_file_mode(
                api_node_leaf,
                stat.S_IWUSR
                | stat.S_IRUSR
                | stat.S_IWGRP
                | stat.S_IRGRP
                | stat.S_IWOTH
                | stat.S_IROTH,
            )

        api_leaf_file.write(
            "0\n"
        )  # event `access` in notify can't be trigger on empty file

    # create params as files
    counter = 0
    params_count = len(rparams)
    if params_count != 0:
        params_10based = int(log10(params_count)) + 1
        param_digit_format = "{:0" + str(params_10based) + "d}"
        for param in rparams:
            param_name, param_value = param.split("=")
            param_name_path = os.path.join(api_node, param_digit_format.format(counter) + "." + param_name)
            counter += 1

            with open(param_name_path, "w") as api_file_param:
                api_file_param.write(param_value)
                append_file_mode(
                    param_name_path,
                    stat.S_IWUSR
                    | stat.S_IRUSR
                    | stat.S_IWGRP
                    | stat.S_IRGRP
                    | stat.S_IWOTH
                    | stat.S_IROTH,
                )

    return api_node, api_req_node


def compose_script_for_dev_name(script_name):
    return f"{script_name}_exec.sh"


EMPTY_DEV_SCRIPT_MARK = "<TODO: THE SCRIPT IS EMPTY>"

def make_default_script(script):
    script.write(
        f"#!/usr/bin/bash\n\n. ${1}/setenv.sh\n\nRESULT_FILE=${2}_result\n\n{EMPTY_DEV_SCRIPT_MARK}"
    )


def make_script_watch_list(script):
    body = (
        r"#!/usr/bin/bash",
        r"",
        r"API_NODE=${1}",
        r". $2/setenv.sh",
        r"RESULT_FILE=${3}_result",
        r'CMD_ARGS=""',
        r'for entry in "${API_NODE}"/*.*',
        r"do",
        r"    file_basename=${entry##*/}",
        r"    param_name=${file_basename#*.}",
        r"    readarray -t arr < ${entry}",
        r"    brr+=(${param_name})",
        r"    for a in ${arr[@]}",
        r"    do",
        r"        if [[ ${a} == \"* ]];",
        r"        then",
        r'            brr+=("${a}")',
        r"        else",
        r"            brr+=(${a})",
        r"        fi",
        r"    done",
        r"done",
        r'echo "${brr[@]}" | xargs find ${REPO_PATH} > ${RESULT_FILE}.txt',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_watch_list_help():
    return "find --help"

def make_script_statistic(script):
    body = (
        r"#!/usr/bin/bash",
        r"",
        r"API_NODE=${1}",
        r". $2/setenv.sh",
        r"RESULT_FILE=${3}_result",
        r'CMD_ARGS=""',
        r'for entry in "${API_NODE}"/*.*',
        r"do",
        r"    file_basename=${entry##*/}",
        r"    param_name=${file_basename#*.}",
        r"    readarray -t arr < ${entry}",
        r"    brr+=(${param_name})",
        r"    for a in ${arr[@]}",
        r"    do",
        r"        if [[ ${a} == \"* ]];",
        r"        then",
        r'            brr+=("${a}")',
        r"        else",
        r"            brr+=(${a})",
        r"        fi",
        r"    done",
        r"done",
        r'echo "${brr[@]}"',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_statistic_help():
    return "${WORK_DIR}/pmccabe_visualizer/pmccabe_build.py --help"

def make_script_view(script):
    body = (
        r"#!/usr/bin/bash",
        r"",
        r"API_NODE=${1}",
        r". $2/setenv.sh",
        r"RESULT_FILE=${3}_result",
        r'CMD_ARGS=""',
        r'for entry in "${API_NODE}"/*.*',
        r"do",
        r"    file_basename=${entry##*/}",
        r"    param_name=${file_basename#*.}",
        r"    readarray -t arr < ${entry}",
        r"    brr+=(${param_name})",
        r"    for a in ${arr[@]}",
        r"    do",
        r"        if [[ ${a} == \"* ]];",
        r"        then",
        r'            brr+=("${a}")',
        r"        else",
        r"            brr+=(${a})",
        r"        fi",
        r"    done",
        r"done",
        r"${WORK_DIR}/watch_list_exec.sh ${SHARED_API_DIR}/project/{uuid} ${WORK_DIR} ${API_NODE}/GET/.watch_list",
        r"cat ${API_NODE}/GET/.watch_list_result.txt | ${WORK_DIR}/pmccabe_visualizer/pmccabe_build.py `${WORK_DIR}/statistic_exec.sh ${SHARED_API_DIR}/project/{uuid}/statistic ${WORK_DIR} stst` > ${RESULT_FILE}.xml",
        r"cat ${RESULT_FILE}.xml | ${WORK_DIR}/pmccabe_visualizer/collapse.py ${brr[@]} > ${RESULT_FILE}.data",
    )
    script.writelines(line + "\n" for line in body)

def generate_script_view_help():
    return "${WORK_DIR}/pmccabe_visualizer/collapse.py --help"

def make_script_flamegraph(script):
    body = (
        r"#!/usr/bin/bash",
        r"",
        r"API_NODE=${1}",
        r". $2/setenv.sh",
        r"RESULT_FILE=${3}_result",
        r'CMD_ARGS=""',
        r'for entry in "${API_NODE}"/*.*',
        r"do",
        r"    file_basename=${entry##*/}",
        r"    param_name=${file_basename#*.}",
        r"    readarray -t arr < ${entry}",
        r"    brr+=(${param_name})",
        r"    for a in ${arr[@]}",
        r"    do",
        r"        if [[ ${a} == \"* ]];",
        r"        then",
        r'            brr+=("${a}")',
        r"        else",
        r"            brr+=(${a})",
        r"        fi",
        r"    done",
        r"done",
        r"${WORK_DIR}/view_exec.sh ${SHARED_API_DIR}/project/{uuid}/statistic/view ${WORK_DIR} ${API_NODE}/GET/.collapsed",
        r"cat ${API_NODE}/GET/.collapsed_result.data | ${WORK_DIR}/FlameGraph/flamegraph.pl ${brr[@]} > ${RESULT_FILE}.svg",
    )
    script.writelines(line + "\n" for line in body)

def generate_script_flamegraph_help():
    return "${WORK_DIR}/FlameGraph/flamegraph.pl --help"


def make_script_analytic(script):
    body = (
        r"#!/usr/bin/bash",
        r"",
        r"API_NODE=${1}",
        r". $2/setenv.sh",
        r"RESULT_FILE=${3}_result",
        r'CMD_ARGS=""',
        r'for entry in "${API_NODE}"/*.*',
        r"do",
        r"    file_basename=${entry##*/}",
        r"    param_name=${file_basename#*.}",
        r"    readarray -t arr < ${entry}",
        r"    special_kind_param_name=${param_name%.*}",
        r"    if [[ ${special_kind_param_name} != 'NO_NAME_PARAM' ]];",
        r"    then",
        r"        brr+=(${param_name})",
        r"    fi",
        r"    for a in ${arr[@]}",
        r"    do",
        r"        if [[ ${a} == \"* ]];",
        r"        then",
        r'            brr+=("${a}")',
        r"        else",
        r"            brr+=(${a})",
        r"        fi",
        r"    done",
        r"done",
        r'echo "${brr[@]}"',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_analytic_help():
    return "rrdtool -h"

def make_script_rrd(script):
    body = (
        r"#!/usr/bin/bash",
        r"",
        r"API_NODE=${1}",
        r". $2/setenv.sh",
        r"RESULT_FILE=${3}_result",
        r'CMD_ARGS=""',
        r'for entry in "${API_NODE}"/*.*',
        r"do",
        r"    file_basename=${entry##*/}",
        r"    param_name=${file_basename#*.}",
        r"    readarray -t arr < ${entry}",
        r"    special_kind_param_name=${param_name%.*}",
        r"    if [[ ${special_kind_param_name} != 'NO_NAME_PARAM' ]];",
        r"    then",
        r"        brr+=(${param_name})",
        r"    fi",
        r"    for a in ${arr[@]}",
        r"    do",
        r"        if [[ ${a} == \"* ]];",
        r"        then",
        r'            brr+=("${a}")',
        r"        else",
        r"            brr+=(${a})",
        r"        fi",
        r"    done",
        r"done",
        r'echo "${brr[@]}"',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_rrd_help():
    return "rrdtool -h"

def make_script_rrd_collect(script):
    body = (
        r"#!/usr/bin/bash",
        r"",
        r"API_NODE=${1}",
        r". $2/setenv.sh",
        r"RESULT_FILE=${3}_result",
        r'CMD_ARGS=""',
        r'for entry in "${API_NODE}"/*.*',
        r"do",
        r"    file_basename=${entry##*/}",
        r"    param_name=${file_basename#*.}",
        r"    readarray -t arr < ${entry}",
        r"    special_kind_param_name=${param_name%.*}",
        r"    if [[ ${special_kind_param_name} != 'NO_NAME_PARAM' ]];",
        r"    then",
        r"        brr+=(${param_name})",
        r"    fi",
        r"    for a in ${arr[@]}",
        r"    do",
        r"        if [[ ${a} == \"* ]];",
        r"        then",
        r'            brr+=("${a}")',
        r"        else",
        r"            brr+=(${a})",
        r"        fi",
        r"    done",
        r"done",
        r'cat ${SHARED_API_DIR}/init.xml | ${WORK_DIR}/build_rrd.py "`${WORK_DIR}/rrd_exec.sh ${SHARED_API_DIR}/project/{uuid}/analytic/rrd ${WORK_DIR} rd`" ${SHARED_API_DIR} ${brr[@]}',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_rrd_collect_help():
    return "rrdtool -h"

def make_script_rrd_select(script):
    body = (
        r"#!/usr/bin/bash",
        r"",
        r"API_NODE=${1}",
        r". $2/setenv.sh",
        r"RESULT_FILE=${3}_result",
        r'CMD_ARGS=""',
        r'for entry in "${API_NODE}"/*.*',
        r"do",
        r"    file_basename=${entry##*/}",
        r"    param_name=${file_basename#*.}",
        r"    readarray -t arr < ${entry}",
        r"    special_kind_param_name=${param_name%.*}",
        r"    if [[ ${special_kind_param_name} != 'NO_NAME_PARAM' ]];",
        r"    then",
        r"        brr+=(${param_name})",
        r"    fi",
        r"    for a in ${arr[@]}",
        r"    do",
        r"        if [[ ${a} == \"* ]];",
        r"        then",
        r'            brr+=("${a}")',
        r"        else",
        r"            brr+=(${a})",
        r"        fi",
        r"    done",
        r"done",
        r'echo "${brr[@]}"',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_rrd_select_help():
    return "rrdtool -h"

def make_script_rrd_view(script):
    body = (
        r"#!/usr/bin/bash",
        r"",
        r"API_NODE=${1}",
        r". $2/setenv.sh",
        r"RESULT_FILE=${3}_result",
        r'echo "`${WORK_DIR}/rrd_select_exec.sh ${SHARED_API_DIR}/project/{uuid}/analytic/rrd/select ${WORK_DIR} se`" | xargs find ${RRD_ROOT} | ${WORK_DIR}/fetch_rrd.py ${SHARED_API_DIR}/project/{uuid}/analytic/rrd/select/view > ${RESULT_FILE}_csv_in_progress',
        r'mv ${RESULT_FILE}_csv_in_progress ${RESULT_FILE}.csv'
    )
    script.writelines(line + "\n" for line in body)

def generate_script_rrd_view_help():
    return "rrdtool -h"

def make_script_rrd_view_graph(script):
    body = (
        r"#!/usr/bin/bash",
        r"",
        r"API_NODE=${1}",
        r". $2/setenv.sh",
        r"RESULT_FILE=${3}_result",
    )
    script.writelines(line + "\n" for line in body)

def generate_script_rrd_view_graph_help():
    return "rrdtool -h"

scripts_generator = {
    "watch_list": make_script_watch_list,
    "statistic": make_script_statistic,
    "view": make_script_view,
    "flamegraph": make_script_flamegraph,
    "analytic": make_script_analytic,
    "rrd": make_script_rrd,
    "rrd_collect": make_script_rrd_collect,
    "rrd_select": make_script_rrd_select,
    "rrd_view": make_script_rrd_view,
    "rrd_view_graph": make_script_rrd_view_graph
}

scripts_help_generator = {
    "watch_list": generate_script_watch_list_help,
    "statistic": generate_script_statistic_help,
    "view": generate_script_view_help,
    "flamegraph": generate_script_flamegraph_help,
    "analytic": generate_script_analytic_help,
    "rrd": generate_script_rrd_help,
    "rrd_collect": generate_script_rrd_collect_help,
    "rrd_select": generate_script_rrd_select_help,
    "rrd_view": generate_script_rrd_view_help,
    "rrd_view_graph": generate_script_rrd_view_graph_help
}


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
                raise NotImplementedError(
                    f'Script "{script_name_generated}" must be implemented, path: {script_generated_path}'
                )

    return script_name_generated


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

parser.add_argument("mode", help=f"Script execution mode: {EXEC_MODE}")

parser.add_argument("api_file", help="Path to file with API description")

parser.add_argument("mount_point", help="destination to build file-system nodes")


args = parser.parse_args()
if args.mode not in EXEC_MODE:
    raise Exception(
        f"Invalid execution mode: {args.mode}. Supported values: {EXEC_MODE}"
    )

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

generated_api_server_scripts_path = "services"
os.makedirs(generated_api_server_scripts_path, exist_ok=True)

errors_detected = []
with open(args.api_file, "r") as api_file:
    for request_line in api_file:
        request_params = [s.strip() for s in request_line.split("\t")]
        if len(request_params) < 3:
            continue

        (req_name, req_type, req_api, *req_params) = request_params
        """re-create filesystem directory structure based on API query"""
        """must be done in 'run' mode only"""
        if args.mode == EXEC_MODE[EXEC_MODE_IMAGE]:
            create_api_fs_node(args.mount_point, req_api, req_type, req_params)
            continue

        api_node, api_req_node = compose_api_fs_node_name(
                args.mount_point, req_api, req_type
            )

        """in 'devel' mode this builder must generate stub files for API request to implement"""
        """must be done BEFORE docker image crafted"""
        if args.mode == EXEC_MODE[EXEC_MODE_DEV]:
            try:
                req_executor_name = create_script_for_dev(
                    generated_api_server_scripts_path, req_name
                )
            except FileExistsError as e:
                print(
                    f'Skipping the script "{req_name}" creation in "{EXEC_MODE[EXEC_MODE_DEV]}":\n\t"{e}"'
                )
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

        """must not generate served listeners scripts in 'run' mode"""
        api_server_script_file_name = f"{req_name}_listener.sh"
        api_server_script_file_path = os.path.join(
            generated_api_server_scripts_path, api_server_script_file_name
        )

        """In dev mode generate it in testing purposes"""
        if args.mode == EXEC_MODE[EXEC_MODE_DEV]:
            api_server_script_file_path += ".test_only"

        with open(api_server_script_file_path, "w") as listener_file:
            api_schema_concrete = api_schema.copy()
            api_schema_concrete[1] = api_schema_concrete[1].format(
                scripts_help_generator[req_name](), api_node
            )
            api_schema_concrete[3] = api_schema_concrete[3].format(
                api_req_node, get_fs_watch_event_for_request_type(req_type), "exec$"
            )
            api_schema_concrete[8] = api_schema_concrete[8].format(
                "{WORK_DIR}",
                req_executor_name,
                api_node,
                "{WORK_DIR}",
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
