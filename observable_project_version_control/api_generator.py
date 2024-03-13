#!/usr/bin/python

import api_fs_exec_utils

"""
Provides a functions set which manages to generate API executor scripts
"""

def make_script_git(script, desired_file_ext=""):
    file_extension = "." + desired_file_ext

    body = (
        *api_fs_exec_utils.generate_exec_header(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'cd ${INITIAL_PROJECT_LOCATION} && echo "${brr[@]}" | xargs git',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_git_help():
    return "git --help"

def get():
    scripts_generator = {
        "git": make_script_git
    }

    scripts_help_generator = {
        "git": generate_script_git_help
    }
    return scripts_generator, scripts_help_generator
