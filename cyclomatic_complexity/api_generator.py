#!/usr/bin/python

import api_fs_exec_utils
import api_fs_bash_utils

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
        *api_fs_bash_utils.generate_extract_attr_value_from_string(), r"",
        *api_fs_bash_utils.generate_add_suffix_if_exist(), r"",
        *api_fs_bash_utils.generate_wait_until_pipe_exist(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        api_fs_bash_utils.extract_attr_value_from_string() + " \"SESSION_ID\" \"${2}\" \"\" '=' SESSION_ID_VALUE", r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'echo "${OVERRIDEN_CMD_ARGS[@]}" | xargs find ${INITIAL_PROJECT_LOCATION}',
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
        *api_fs_bash_utils.generate_extract_attr_value_from_string(), r"",
        *api_fs_bash_utils.generate_add_suffix_if_exist(), r"",
        *api_fs_bash_utils.generate_wait_until_pipe_exist(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        api_fs_bash_utils.extract_attr_value_from_string() + " \"SESSION_ID\" \"${2}\" \"\" '=' SESSION_ID_VALUE", r"",
        api_fs_bash_utils.add_suffix_if_exist() + " \"${SESSION_ID_VALUE}\" \"result.txt\" MULTISESSION_PIPE_OUT_WATCH_LIST", r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'echo "${IN_SERVER_REQUEST_ARGS[@]}" > ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cyclomatic_complexity/GET/exec',
        api_fs_bash_utils.wait_until_pipe_exist() + " ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cyclomatic_complexity/GET/${MULTISESSION_PIPE_OUT_WATCH_LIST}",
        r"cat ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cyclomatic_complexity/GET/${MULTISESSION_PIPE_OUT_WATCH_LIST} | ${WORK_DIR}/pmccabe_visualizer/pmccabe_build.py ${OVERRIDEN_CMD_ARGS[@]}",
        r"if [ ! -z ${SESSION_ID_VALUE} ]; then rm -f ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cyclomatic_complexity/GET/${MULTISESSION_PIPE_OUT_WATCH_LIST}; fi"
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
        *api_fs_bash_utils.generate_extract_attr_value_from_string(), r"",
        *api_fs_bash_utils.generate_add_suffix_if_exist(), r"",
        *api_fs_bash_utils.generate_wait_until_pipe_exist(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        api_fs_bash_utils.extract_attr_value_from_string() + " \"SESSION_ID\" \"${2}\" \"\" '=' SESSION_ID_VALUE", r"",
        api_fs_bash_utils.add_suffix_if_exist() + " \"${SESSION_ID_VALUE}\" \"result.xml\" MULTISESSION_PIPE_OUT", r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'echo "${IN_SERVER_REQUEST_ARGS[@]}" > ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cyclomatic_complexity/statistic/GET/exec',
        api_fs_bash_utils.wait_until_pipe_exist() + " ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cyclomatic_complexity/statistic/GET/${MULTISESSION_PIPE_OUT}",
        r"cat ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cyclomatic_complexity/statistic/GET/${MULTISESSION_PIPE_OUT} | ${WORK_DIR}/pmccabe_visualizer/collapse.py ${OVERRIDEN_CMD_ARGS[@]}",
        r"if [ ! -z ${SESSION_ID_VALUE} ]; then rm -f ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cyclomatic_complexity/statistic/GET/${MULTISESSION_PIPE_OUT}; fi"
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
        *api_fs_bash_utils.generate_extract_attr_value_from_string(), r"",
        *api_fs_bash_utils.generate_add_suffix_if_exist(), r"",
        *api_fs_bash_utils.generate_wait_until_pipe_exist(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        api_fs_bash_utils.extract_attr_value_from_string() + " \"SESSION_ID\" \"${2}\" \"\" '=' SESSION_ID_VALUE", r"",
        api_fs_bash_utils.add_suffix_if_exist() + " \"${SESSION_ID_VALUE}\" \"result.txt\" MULTISESSION_PIPE_OUT", r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'echo "${IN_SERVER_REQUEST_ARGS[@]}" > ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cyclomatic_complexity/statistic/view/GET/exec',
        api_fs_bash_utils.wait_until_pipe_exist() + " ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cyclomatic_complexity/statistic/view/GET/${MULTISESSION_PIPE_OUT}",
        r"cat ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cyclomatic_complexity/statistic/view/GET/${MULTISESSION_PIPE_OUT} | ${WORK_DIR}/FlameGraph/flamegraph.pl ${OVERRIDEN_CMD_ARGS[@]}",
        r"if [ ! -z ${SESSION_ID_VALUE} ]; then rm -f ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cyclomatic_complexity/statistic/view/GET/${MULTISESSION_PIPE_OUT}; fi"
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
