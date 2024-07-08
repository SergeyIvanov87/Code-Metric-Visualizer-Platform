#!/usr/bin/python

import api_fs_exec_utils

"""
Provides a functions set which manages to generate API executor scripts
"""

def make_script_req_1(script, desired_file_ext):
    file_extension = "." + desired_file_ext

    body = (
        *api_fs_exec_utils.generate_exec_header(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'echo "${OVERRIDEN_CMD_ARGS[@]}"',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_req_1_help():
    return "Help req_1 "

def make_script_req_2(script, desired_file_ext):
    file_extension = "." + desired_file_ext

    body = (
        *api_fs_exec_utils.generate_exec_header(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'echo "${OVERRIDEN_CMD_ARGS[@]}"',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_req_2_help():
    return "Help req_2"

def make_script_req_3(script, desired_file_ext):
    file_extension = "." + desired_file_ext

    body = (
        *api_fs_exec_utils.generate_exec_header(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'echo "${OVERRIDEN_CMD_ARGS[@]}"',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_req_3_help():
    return "Help req_3"

def get():
    scripts_generator = {
        "req_1": make_script_req_1,
        "req_2": make_script_req_2,
        "req_3": make_script_req_3
    }

    scripts_help_generator = {
        "req_1": generate_script_req_1_help,
        "req_2": generate_script_req_2_help,
        "req_3": generate_script_req_3_help
    }
    return scripts_generator, scripts_help_generator
