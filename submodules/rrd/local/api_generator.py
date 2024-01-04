#!/usr/bin/python


def make_script_analytic(script):
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
        r"API_NODE=${2}",
        r". ${1}/setenv.sh",
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
        r"API_NODE=${2}",
        r". ${1}/setenv.sh",
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
        r'cat ${SHARED_API_DIR}/init.xml | ${WORK_DIR}/build_rrd.py "`${WORK_DIR}/rrd_exec.sh ${MAIN_IMAGE_ENV_SHARED_LOCATION} ${SHARED_API_DIR}/analytic/rrd rd`" ${SHARED_API_DIR} ${brr[@]}',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_rrd_collect_help():
    return "rrdtool -h"

def make_script_rrd_select(script):
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
        r"API_NODE=${2}",
        r". ${1}/setenv.sh",
        r"RESULT_FILE=${3}_result",
        r'echo "`${WORK_DIR}/rrd_select_exec.sh ${MAIN_IMAGE_ENV_SHARED_LOCATION} ${SHARED_API_DIR}/analytic/rrd/select se`" | xargs find ${RRD_ROOT} | ${WORK_DIR}/fetch_rrd.py ${SHARED_API_DIR}/analytic/rrd/select/view > ${RESULT_FILE}_csv_in_progress',
        r'mv ${RESULT_FILE}_csv_in_progress ${RESULT_FILE}.csv'
    )
    script.writelines(line + "\n" for line in body)

def generate_script_rrd_view_help():
    return "rrdtool -h"

def make_script_rrd_view_graph(script):
    body = (
        r"#!/usr/bin/bash",
        r"",
        r"API_NODE=${2}",
        r". ${1}/setenv.sh",
        r"RESULT_FILE=${3}_result",
        r'echo "`${WORK_DIR}/rrd_select_exec.sh ${MAIN_IMAGE_ENV_SHARED_LOCATION} ${SHARED_API_DIR}/analytic/rrd/select se`" | xargs find ${RRD_ROOT} | ${WORK_DIR}/graph_rrd.py ${SHARED_API_DIR}/analytic/rrd/select/view/graph ${RESULT_FILE}',
    )

    script.writelines(line + "\n" for line in body)

def generate_script_rrd_view_graph_help():
    return "rrdtool -h"



def get():
    scripts_generator = {
        "analytic": make_script_analytic,
        "rrd": make_script_rrd,
        "rrd_collect": make_script_rrd_collect,
        "rrd_select": make_script_rrd_select,
        "rrd_view": make_script_rrd_view,
        "rrd_view_graph": make_script_rrd_view_graph
    }

    scripts_help_generator = {
        "analytic": generate_script_analytic_help,
        "rrd": generate_script_rrd_help,
        "rrd_collect": generate_script_rrd_collect_help,
        "rrd_select": generate_script_rrd_select_help,
        "rrd_view": generate_script_rrd_view_help,
        "rrd_view_graph": generate_script_rrd_view_graph_help
    }
    return scripts_generator, scripts_help_generator
