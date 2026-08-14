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
        api_fs_bash_utils.extract_attr_value_from_string() + " \"doc_data\" \"${2}\" \"\" '=' DOC_DATA_VALUE", r"",
        r'document_data="${DOC_DATA_VALUE}"',
        r'OVERRIDEN_CMD_ARGS=( "${OVERRIDEN_CMD_ARGS[@]/doc_data}" )',
        r'if [ ! -z "${document_data}" ]; then',
        r'  OVERRIDEN_CMD_ARGS=( "${OVERRIDEN_CMD_ARGS[@]/$document_data}" )',
        r'fi',
        "echo \"${OVERRIDEN_CMD_ARGS[@]}\" | xargs -I% -- sh -c \"echo '${document_data}' | ${WORK_DIR}/attach_doc_chunk.py %\""
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
        api_fs_bash_utils.extract_attr_value_from_string() + " \"-URI\" \"${2}\" \"\" '=' URI_VALUE", r"",
        api_fs_bash_utils.extract_attr_value_from_string() + " \"doc_data\" \"${2}\" \"\" '=' DOC_DATA_VALUE", r"",
        r'if [ -z "${URI_VALUE}" ]; then',
        r'  OVERRIDEN_CMD_ARGS=( "${OVERRIDEN_CMD_ARGS[@]/-URI}" )',
        r'fi',
        r'document_data="${DOC_DATA_VALUE}"',
        r'OVERRIDEN_CMD_ARGS=( "${OVERRIDEN_CMD_ARGS[@]/doc_data}" )',
        r'if [ ! -z "${document_data}" ]; then',
        r'  OVERRIDEN_CMD_ARGS=( "${OVERRIDEN_CMD_ARGS[@]/$document_data}" )',
        r'fi',
        "echo \"${OVERRIDEN_CMD_ARGS[@]}\" | xargs -I% -- sh -c \"echo '${document_data}' | ${WORK_DIR}/put_doc.py %\""
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

def make_get_docs(script, desired_file_ext=""):
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
        r'echo "${OVERRIDEN_CMD_ARGS[@]}" | xargs ${WORK_DIR}/get_docs.py'
    )
    script.writelines(line + "\n" for line in body)


def make_get_docs_help():
    return "make_get_docs_help"


def make_get_doc_info(script, desired_file_ext=""):
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
        r'echo "${OVERRIDEN_CMD_ARGS[@]}" | xargs ${WORK_DIR}/get_doc_info.py'
    )
    script.writelines(line + "\n" for line in body)


def make_get_doc_info_help():
    return "make_get_doc_info_help"


def get():
    scripts_generator = {
        "attach_doc_chunk": make_attach_doc_chunk,
        "delete_doc": make_delete_doc,
        "get_doc_info": make_get_doc_info,
        "get_docs": make_get_docs,
        "put_doc": make_put_doc,
        "sync": make_sync
    }

    scripts_help_generator = {
        "attach_doc_chunk": make_attach_doc_chunk_help,
        "delete_doc": make_delete_doc_help,
        "get_doc_info": make_get_doc_info_help,
        "get_docs": make_get_docs_help,
        "put_doc": make_put_doc_help,
        "sync": make_sync_help
    }
    return scripts_generator, scripts_help_generator
