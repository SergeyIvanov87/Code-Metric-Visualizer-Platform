#!/usr/bin/python

"""
Provides a functions set which manage to generate API executor scripts
"""

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
        r'echo "`${WORK_DIR}/rrd_select_exec.sh ${SHARED_API_DIR}/project/{uuid}/analytic/rrd/select ${WORK_DIR} se`" | xargs find ${RRD_ROOT} | ${WORK_DIR}/graph_rrd.py ${SHARED_API_DIR}/project/{uuid}/analytic/rrd/select/view/graph ${RESULT_FILE}',
    )

    script.writelines(line + "\n" for line in body)

def generate_script_rrd_view_graph_help():
    return "rrdtool -h"

def get():
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
    return scripts_generator, scripts_help_generator
