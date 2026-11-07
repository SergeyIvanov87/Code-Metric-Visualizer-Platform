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

def make_script_req_4(script, desired_file_ext):
    file_extension = "." + desired_file_ext

    body = (
        *api_fs_exec_utils.generate_exec_header(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'echo "${OVERRIDEN_CMD_ARGS[@]}"',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_req_4_help():
    return "Help req_4 "

def make_script_req_5(script, desired_file_ext):
    file_extension = "." + desired_file_ext

    body = (
        *api_fs_exec_utils.generate_exec_header(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'echo "${OVERRIDEN_CMD_ARGS[@]}"',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_req_5_help():
    return "Help req_5 "

def make_script_req_6(script, desired_file_ext):
    file_extension = "." + desired_file_ext

    body = (
        *api_fs_exec_utils.generate_exec_header(), r"",
        *api_fs_exec_utils.generate_get_result_type(file_extension), r"",
        *api_fs_exec_utils.generate_api_node_env_init(), r"",
        *api_fs_exec_utils.generate_read_api_fs_args(), r"",
        r'echo "${OVERRIDEN_CMD_ARGS[@]}"',
    )
    script.writelines(line + "\n" for line in body)

def generate_script_req_6_help():
    return "Help req_6 "

def make_script_response_json(script, desired_file_ext):
    script.writelines(line + "\n" for line in (
        *api_fs_exec_utils.generate_exec_header(),
        *api_fs_exec_utils.generate_get_result_type("." + desired_file_ext),
        'printf \'%s\' \'{"auth":true,"message":"<b id=server-markup>JSON</b>"}\'',
    ))


def make_script_response_text(script, desired_file_ext):
    script.writelines(line + "\n" for line in (
        *api_fs_exec_utils.generate_exec_header(),
        *api_fs_exec_utils.generate_get_result_type("." + desired_file_ext),
        r"printf '%s' 'Plain text <b id=server-markup>response</b>'",
    ))


def make_script_response_image(script, desired_file_ext):
    script.writelines(line + "\n" for line in (
        *api_fs_exec_utils.generate_exec_header(),
        *api_fs_exec_utils.generate_get_result_type("." + desired_file_ext),
        'printf \'%s\' \'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"><rect width="1200" height="800" fill="steelblue"/></svg>\'',
    ))


def make_script_response_binary(script, desired_file_ext):
    script.writelines(line + "\n" for line in (
        *api_fs_exec_utils.generate_exec_header(),
        *api_fs_exec_utils.generate_get_result_type("." + desired_file_ext),
        r"printf '\000\001\377fixture\n'",
    ))


def make_script_response_html(script, desired_file_ext):
    script.writelines(line + "\n" for line in (
        *api_fs_exec_utils.generate_exec_header(),
        *api_fs_exec_utils.generate_get_result_type("." + desired_file_ext),
        "printf '%s' '<html><body><h2>HTML response</h2></body></html>'",
    ))


def make_script_response_xml(script, desired_file_ext):
    script.writelines(line + "\n" for line in (
        *api_fs_exec_utils.generate_exec_header(),
        *api_fs_exec_utils.generate_get_result_type("." + desired_file_ext),
        "printf '%s' '<root><child>XML response</child></root>'",
    ))


def get():
    scripts_generator = {
        "req_1": make_script_req_1,
        "req_4": make_script_req_4,
        "req_2": make_script_req_2,
        "req_5": make_script_req_5,
        "req_3": make_script_req_3,
        "req_6": make_script_req_6,
        "response_json": make_script_response_json,
        "response_text": make_script_response_text,
        "response_image": make_script_response_image,
        "response_html": make_script_response_html,
        "response_xml": make_script_response_xml,
        "response_binary": make_script_response_binary
    }

    scripts_help_generator = {
        "req_1": generate_script_req_1_help,
        "req_4": generate_script_req_4_help,
        "req_2": generate_script_req_2_help,
        "req_5": generate_script_req_5_help,
        "req_3": generate_script_req_3_help,
        "req_6": generate_script_req_6_help
    }
    return scripts_generator, scripts_help_generator
