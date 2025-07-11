#!/usr/bin/python

import api_fs_exec_utils
import api_fs_bash_utils

"""
Provides a functions set which manages to generate API executor scripts
"""

def generate_request_exec_script(req_name, script, desired_file_ext):
    file_extension=""
    if len(desired_file_ext) != 0:
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
        r'$(dirname "$0")/req_cmd.sh',
        r'echo "echo args: ${OVERRIDEN_CMD_ARGS[@]}"',
    )
    script.writelines(line + "\n" for line in body)

def get():
    scripts_generator = {
    }

    scripts_help_generator = {
    }
    return scripts_generator, scripts_help_generator
