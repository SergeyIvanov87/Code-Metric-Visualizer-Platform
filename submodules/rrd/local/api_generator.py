#!/usr/bin/python

import api_generator_utils

def make_script_analytic(script):
    body = (
        *api_generator_utils.generate_exec_header(), r"",
        *api_generator_utils.generate_get_result_type(""), r"",
        *api_generator_utils.generate_api_node_env_init(), r"",
        *api_generator_utils.generate_read_api_fs_args(), r"",
        r'echo "${brr[@]}"',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_analytic_help():
    return "rrdtool -h"

def make_script_rrd(script):
    body = (
        *api_generator_utils.generate_exec_header(), r"",
        *api_generator_utils.generate_get_result_type(""), r"",
        *api_generator_utils.generate_api_node_env_init(), r"",
        *api_generator_utils.generate_read_api_fs_args(), r"",
        r'echo "${brr[@]}"',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_rrd_help():
    return "rrdtool -h"

def make_script_rrd_collect(script):
    body = (
        *api_generator_utils.generate_exec_header(), r"",
        *api_generator_utils.generate_get_result_type(""), r"",
        *api_generator_utils.generate_api_node_env_init(), r"",
        *api_generator_utils.generate_read_api_fs_args(), r"",
        r'echo 0 > ${SHARED_API_DIR}/analytic/rrd/PUT/exec',
        r'RRD_DB_PARAMS=`cat ${SHARED_API_DIR}/analytic/rrd/PUT/result`',
        r'echo "-mmcc=1 -tmcc=1 -sif=1 -lif=1" > ${SHARED_API_DIR}/main/statistic/GET/exec',
        r'cat ${SHARED_API_DIR}/main/statistic/GET/result.xml | ${WORK_DIR}/build_rrd.py "${RRD_DB_PARAMS}" ${SHARED_API_DIR} ${brr[@]}',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_rrd_collect_help():
    return "rrdtool -h"

def make_script_rrd_select(script):
    body = (
        *api_generator_utils.generate_exec_header(), r"",
        *api_generator_utils.generate_get_result_type(""), r"",
        *api_generator_utils.generate_api_node_env_init(), r"",
        *api_generator_utils.generate_read_api_fs_args(), r"",
        r'echo "${brr[@]}"',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_rrd_select_help():
    return "rrdtool -h"

def make_script_rrd_view(script):
    body = (
        *api_generator_utils.generate_exec_header(), r"",
        *api_generator_utils.generate_get_result_type(".csv"), r"",
        *api_generator_utils.generate_api_node_env_init(), r"",
        r'echo 0 > ${SHARED_API_DIR}/analytic/rrd/select/PUT/exec',
        r'cat ${SHARED_API_DIR}/analytic/rrd/select/PUT/result | xargs find ${RRD_ROOT} | ${WORK_DIR}/fetch_rrd.py ${SHARED_API_DIR}/analytic/rrd/select/view',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_rrd_view_help():
    return "rrdtool -h"

def make_script_rrd_view_graph(script):
    body = (
        *api_generator_utils.generate_exec_header(), r"",
        *api_generator_utils.generate_get_result_type(".png"), r"",
        *api_generator_utils.generate_api_node_env_init(), r"",
        r"RESULT_FILE=`mktemp -u`",
        r'echo 0 > ${SHARED_API_DIR}/analytic/rrd/select/PUT/exec',
        r'cat ${SHARED_API_DIR}/analytic/rrd/select/PUT/result | xargs find ${RRD_ROOT} | ${WORK_DIR}/graph_rrd.py ${SHARED_API_DIR}/analytic/rrd/select/view/graph ${RESULT_FILE}',
        r'cat ${RESULT_FILE}.png',
        r'rm -f ${RESULT_FILE}.png'
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
