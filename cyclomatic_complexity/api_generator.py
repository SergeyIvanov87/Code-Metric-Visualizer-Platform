#!/usr/bin/python

import api_fs_exec_utils

"""
Provides a functions set which manages to generate API executor scripts
"""

def make_script_watch_list(script, desired_file_ext=""):
    if len(desired_file_ext) == 0:
        file_extension = ".txt"
    else:
        file_extension = "." + desired_file_ext

    body = (
        *api_fs_exec_utils.generate_exec_header(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'echo "${brr[@]}" | xargs find ${INITIAL_PROJECT_LOCATION}',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_watch_list_help():
    return "find --help"

def make_script_statistic(script, desired_file_ext=""):
    if len(desired_file_ext) == 0:
        file_extension = ".xml"
    else:
        file_extension = "." + desired_file_ext

    body = (
        *api_fs_exec_utils.generate_exec_header(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'echo "${IN_ARGS[@]}" > ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/GET/exec',
        r"cat ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/GET/result.txt | ${WORK_DIR}/pmccabe_visualizer/pmccabe_build.py ${brr[@]}",
    )
    script.writelines(line + "\n" for line in body)

def generate_script_statistic_help():
    return "${WORK_DIR}/pmccabe_visualizer/pmccabe_build.py --help"

def make_script_view(script, desired_file_ext=""):
    if len(desired_file_ext) == 0:
        file_extension = ".txt"
    else:
        file_extension = "." + desired_file_ext

    body = (
        *api_fs_exec_utils.generate_exec_header(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'echo "${IN_ARGS[@]}" > ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/statistic/GET/exec',
        r"cat ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/statistic/GET/result.xml | ${WORK_DIR}/pmccabe_visualizer/collapse.py ${brr[@]}",
    )
    script.writelines(line + "\n" for line in body)

def generate_script_view_help():
    return "${WORK_DIR}/pmccabe_visualizer/collapse.py --help"

def make_script_flamegraph(script, desired_file_ext=""):
    if len(desired_file_ext) == 0:
        file_extension = ".svg"
    else:
        file_extension = "." + desired_file_ext

    body = (
        *api_fs_exec_utils.generate_exec_header(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'echo "${IN_ARGS[@]}" > ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/statistic/view/GET/exec',
        r"cat ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/statistic/view/GET/result.txt | ${WORK_DIR}/FlameGraph/flamegraph.pl ${brr[@]}",
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
