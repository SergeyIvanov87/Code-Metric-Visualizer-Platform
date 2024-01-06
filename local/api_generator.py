#!/usr/bin/python

"""
Provides a functions set which manages to generate API executor scripts
"""

def make_script_watch_list(script):
    body = (
        r"#!/usr/bin/bash",
        r"",
        r'if [[ ${1} == "--result_type" ]];',
        r"then",
        r'    echo ".txt"',
        r"    exit 0",
        r"fi",
        r"",
        r"API_NODE=${2}",
        r". ${1}/setenv.sh",
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
        r'echo "${brr[@]}" | xargs find ${INITIAL_PROJECT_LOCATION}',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_watch_list_help():
    return "find --help"

def make_script_statistic(script):
    body = (
        r"#!/usr/bin/bash",
        r"",
        r'if [[ ${1} == "--result_type" ]];',
        r"then",
        r'    echo ""',
        r"    exit 0",
        r"fi",
        r"",
        r"API_NODE=${2}",
        r". ${1}/setenv.sh",
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
        r'if [[ ${1} == "--result_type" ]];',
        r"then",
        r'    echo ".collapsed"',
        r"    exit 0",
        r"fi",
        r"",
        r"API_NODE=${2}",
        r". ${1}/setenv.sh",
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
        r"${WORK_DIR}/watch_list_exec.sh ${MAIN_IMAGE_ENV_SHARED_LOCATION} ${SHARED_API_DIR}/main | ${WORK_DIR}/pmccabe_visualizer/pmccabe_build.py `${WORK_DIR}/statistic_exec.sh ${MAIN_IMAGE_ENV_SHARED_LOCATION} ${SHARED_API_DIR}/main/statistic` | ${WORK_DIR}/pmccabe_visualizer/collapse.py ${brr[@]}",
    )
    script.writelines(line + "\n" for line in body)

def generate_script_view_help():
    return "${WORK_DIR}/pmccabe_visualizer/collapse.py --help"

def make_script_flamegraph(script):
    body = (
        r"#!/usr/bin/bash",
        r"",
        r'if [[ ${1} == "--result_type" ]];',
        r"then",
        r'    echo ".svg"',
        r"    exit 0",
        r"fi",
        r"",
        r"API_NODE=${2}",
        r". ${1}/setenv.sh",
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
        r"${WORK_DIR}/view_exec.sh ${MAIN_IMAGE_ENV_SHARED_LOCATION} ${SHARED_API_DIR}/main/statistic/view ${API_NODE}/GET/.collapsed | ${WORK_DIR}/FlameGraph/flamegraph.pl ${brr[@]}",
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
