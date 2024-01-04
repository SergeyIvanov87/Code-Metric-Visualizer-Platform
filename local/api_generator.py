#!/usr/bin/python

"""
Provides a functions set which manages to generate API executor scripts
"""

def make_script_watch_list(script):
    body = (
        r"#!/usr/bin/bash",
        r"",
        r"API_NODE=${2}",
        r". ${1}/setenv.sh",
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
        r'echo "${brr[@]}" | xargs find ${INITIAL_PROJECT_LOCATION} > ${RESULT_FILE}.txt',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_watch_list_help():
    return "find --help"

def make_script_statistic(script):
    body = (
        r"#!/usr/bin/bash",
        r"",
        r"API_NODE=${2}",
        r". ${1}/setenv.sh",
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
        r"API_NODE=${2}",
        r". ${1}/setenv.sh",
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
        r"${WORK_DIR}/watch_list_exec.sh ${MAIN_IMAGE_ENV_SHARED_LOCATION} ${SHARED_API_DIR}/main ${API_NODE}/GET/.watch_list",
        r"cat ${API_NODE}/GET/.watch_list_result.txt | ${WORK_DIR}/pmccabe_visualizer/pmccabe_build.py `${WORK_DIR}/statistic_exec.sh ${MAIN_IMAGE_ENV_SHARED_LOCATION} ${SHARED_API_DIR}/main/statistic stst` > ${RESULT_FILE}.xml",
        r"cat ${RESULT_FILE}.xml | ${WORK_DIR}/pmccabe_visualizer/collapse.py ${brr[@]} > ${RESULT_FILE}.data",
    )
    script.writelines(line + "\n" for line in body)

def generate_script_view_help():
    return "${WORK_DIR}/pmccabe_visualizer/collapse.py --help"

def make_script_flamegraph(script):
    body = (
        r"#!/usr/bin/bash",
        r"",
        r"API_NODE=${2}",
        r". ${1}/setenv.sh",
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
        r"${WORK_DIR}/view_exec.sh ${MAIN_IMAGE_ENV_SHARED_LOCATION} ${SHARED_API_DIR}/main/statistic/view ${API_NODE}/GET/.collapsed",
        r"cat ${API_NODE}/GET/.collapsed_result.data | ${WORK_DIR}/FlameGraph/flamegraph.pl ${brr[@]} > ${RESULT_FILE}.svg",
    )
    script.writelines(line + "\n" for line in body)

def generate_script_flamegraph_help():
    return "${WORK_DIR}/FlameGraph/flamegraph.pl --help"

def get():
    scripts_generator = {
        "watch_list": make_script_watch_list,
        "statistic": make_script_statistic,
        "view": make_script_view,
        "flamegraph": make_script_flamegraph
    }

    scripts_help_generator = {
        "watch_list": generate_script_watch_list_help,
        "statistic": generate_script_statistic_help,
        "view": generate_script_view_help,
        "flamegraph": generate_script_flamegraph_help
    }
    return scripts_generator, scripts_help_generator
