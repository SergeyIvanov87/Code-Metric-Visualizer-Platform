#!/usr/bin/python

import api_generator_utils

"""
Provides a functions set which manages to generate API executor scripts
"""

def make_script_watch_list(script):
    body = (
        *api_generator_utils.generate_exec_header(), r"",
        *api_generator_utils.generate_get_result_type(".txt"), r"",
        *api_generator_utils.generate_api_node_env_init(), r"",
        *api_generator_utils.generate_read_api_fs_args(), r"",
        r'echo "${brr[@]}" | xargs find ${INITIAL_PROJECT_LOCATION}',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_watch_list_help():
    return "find --help"

def make_script_statistic(script):
    body = (
        *api_generator_utils.generate_exec_header(), r"",
        *api_generator_utils.generate_get_result_type(".xml"), r"",
        *api_generator_utils.generate_api_node_env_init(), r"",
        *api_generator_utils.generate_read_api_fs_args(), r"",
        r"${WORK_DIR}/watch_list_exec.sh ${MAIN_IMAGE_ENV_SHARED_LOCATION} ${SHARED_API_DIR}/main | ${WORK_DIR}/pmccabe_visualizer/pmccabe_build.py ${brr[@]}",
    )
    script.writelines(line + "\n" for line in body)

def generate_script_statistic_help():
    return "${WORK_DIR}/pmccabe_visualizer/pmccabe_build.py --help"

def make_script_view(script):
    body = (
        *api_generator_utils.generate_exec_header(), r"",
        *api_generator_utils.generate_get_result_type(".collapsed"), r"",
        *api_generator_utils.generate_api_node_env_init(), r"",
        *api_generator_utils.generate_read_api_fs_args(), r"",
        r"${WORK_DIR}/statistic_exec.sh ${MAIN_IMAGE_ENV_SHARED_LOCATION} ${SHARED_API_DIR}/main/statistic | ${WORK_DIR}/pmccabe_visualizer/collapse.py ${brr[@]}",
    )
    script.writelines(line + "\n" for line in body)

def generate_script_view_help():
    return "${WORK_DIR}/pmccabe_visualizer/collapse.py --help"

def make_script_flamegraph(script):
    body = (
        *api_generator_utils.generate_exec_header(), r"",
        *api_generator_utils.generate_get_result_type(".svg"), r"",
        *api_generator_utils.generate_api_node_env_init(), r"",
        *api_generator_utils.generate_read_api_fs_args(), r"",
        r"${WORK_DIR}/view_exec.sh ${MAIN_IMAGE_ENV_SHARED_LOCATION} ${SHARED_API_DIR}/main/statistic/view | ${WORK_DIR}/FlameGraph/flamegraph.pl ${brr[@]}",
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
