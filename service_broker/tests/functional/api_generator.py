#!/usr/bin/python

import api_fs_exec_utils

"""
Provides a functions set which manages to generate API executor scripts
"""
def generate_increment_counter_in_file(filename):
    return (
        f'if [ ! -f "{filename}" ]; then echo 0 > {filename}; fi',
        f'let COUNTER=`cat {filename}`+1',
        f'echo $COUNTER > {filename}'
        )

def make_script_git(script, desired_file_ext):
    if len(desired_file_ext) == 0:
        file_extension = ".txt"
    else:
        file_extension = "." + desired_file_ext

    body = (
        *api_fs_exec_utils.generate_exec_header(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        *generate_increment_counter_in_file("/tmp/test/git.counter"), r""
        r'echo $COUNTER',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_git_help():
    return "Help git "

def make_script_rrd(script, desired_file_ext):
    if len(desired_file_ext) == 0:
        file_extension = ""
    else:
        file_extension = "." + desired_file_ext

    body = (
        *api_fs_exec_utils.generate_exec_header(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        *generate_increment_counter_in_file("/tmp/test/rrd.counter"), r""
        r'echo $COUNTER',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_rrd_help():
    return "Help rrd"

def make_script_rrd_collect(script, desired_file_ext):
    if len(desired_file_ext) == 0:
        file_extension = ""
    else:
        file_extension = "." + desired_file_ext

    body = (
        *api_fs_exec_utils.generate_exec_header(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        *generate_increment_counter_in_file("/tmp/test/rrd_collect.counter"), r""
        r'echo $COUNTER',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_rrd_collect_help():
    return "Help rrd_collect"

def get():
    scripts_generator = {
        "git": make_script_git,
        "rrd": make_script_rrd,
        "rrd_collect": make_script_rrd_collect
    }

    scripts_help_generator = {
        "git": generate_script_git_help,
        "rrd": generate_script_rrd_help,
        "rrd_collect": generate_script_rrd_collect_help
    }
    return scripts_generator, scripts_help_generator
