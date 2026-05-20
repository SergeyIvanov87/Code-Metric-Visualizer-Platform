#!/usr/bin/python

import api_fs_exec_utils
import api_fs_bash_utils

"""
Provides a functions set which manages to generate API executor scripts
"""

def make_attach_doc_chunk(script, desired_file_ext=""):
    if len(desired_file_ext) == 0:
        file_extension = ".json"
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
        r'echo "${OVERRIDEN_CMD_ARGS[@]}" | xargs ${WORK_DIR}/attach_doc_chunk.py'
    )
    script.writelines(line + "\n" for line in body)

def make_attach_doc_chunk_help():
    return "make_attach_doc_chunk_help"



def make_delete_doc(script, desired_file_ext=""):
    if len(desired_file_ext) == 0:
        file_extension = ".json"
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
        r'echo "${OVERRIDEN_CMD_ARGS[@]}" | xargs ${WORK_DIR}/delete_doc.py'
    )
    script.writelines(line + "\n" for line in body)

def make_delete_doc_help():
    return "make_delete_doc_help"



def make_put_doc(script, desired_file_ext=""):
    if len(desired_file_ext) == 0:
        file_extension = ".json"
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
        r'echo "${OVERRIDEN_CMD_ARGS[@]}" | xargs ${WORK_DIR}/put_doc.py'
    )
    script.writelines(line + "\n" for line in body)

def make_put_doc_help():
    return "make_put_doc_help"


def make_sync(script, desired_file_ext=""):
    if len(desired_file_ext) == 0:
        file_extension = ".json"
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
        r'echo "${OVERRIDEN_CMD_ARGS[@]}" | xargs ${WORK_DIR}/sync.py'
    )
    script.writelines(line + "\n" for line in body)

def make_sync_help():
    return "make_sync_help"

def get():
    scripts_generator = {
        "attach_doc_chunk": make_attach_doc_chunk,
        "delete_doc": make_delete_doc,
        "put_doc": make_put_doc,
        "sync": make_sync
    }

    scripts_help_generator = {
        "attach_doc_chunk": make_attach_doc_chunk_help,
        "delete_doc": make_delete_doc_help,
        "put_doc": make_put_doc_help,
        "sync": make_sync_help
    }
    return scripts_generator, scripts_help_generator
