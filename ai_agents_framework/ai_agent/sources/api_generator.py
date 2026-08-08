#!/usr/bin/python

import api_fs_exec_utils
import api_fs_bash_utils

"""
Provides a functions set which manages to generate API executor scripts
"""

def make_script_rag_add(script, desired_file_ext=""):
    if len(desired_file_ext) == 0:
        file_extension = ""
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
        "echo \"${OVERRIDEN_CMD_ARGS[@]}\" | xargs -I% -- sh -c \"echo '${document_data}' | ${WORK_DIR}/rag_add.py --session_id='${SESSION_ID_VALUE}' -db_host=${VECTOR_DB_HOST} -db_port=${VECTOR_DB_PORT} % ${SHARED_API_DIR} ${MAIN_SERVICE_NAME}\""
        #r'echo "${OVERRIDEN_CMD_ARGS[@]}" | ${WORK_DIR}/rag_add.py --session_id="${SESSION_ID_VALUE} -db_host=${VECTOR_DB_HOST} -db_port=${VECTOR_DB_PORT}"'
    )
    script.writelines(line + "\n" for line in body)

def make_script_rag_add_help():
    return "make_script_rag_add_help"


def make_script_rag_delete(script, desired_file_ext=""):
    if len(desired_file_ext) == 0:
        file_extension = ""
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
        r'echo "${OVERRIDEN_CMD_ARGS[@]}" | ${WORK_DIR}/rag_delete.py'
    )
    script.writelines(line + "\n" for line in body)

def make_script_rag_delete_help():
    return "make_script_rag_delete_help"



def make_script_rag_list(script, desired_file_ext=""):
    if len(desired_file_ext) == 0:
        file_extension = ""
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
        r'echo "${OVERRIDEN_CMD_ARGS[@]}" | ${WORK_DIR}/rag_list.py'
    )
    script.writelines(line + "\n" for line in body)

def make_script_rag_list_help():
    return "make_script_rag_list_help"


def make_script_ask_question(script, desired_file_ext=""):
    if len(desired_file_ext) == 0:
        file_extension = ""
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
        r'echo "${OVERRIDEN_CMD_ARGS[@]}"'
    )
    script.writelines(line + "\n" for line in body)

def make_script_ask_question_help():
    return "make_script_ask_question_help"



def make_script_hello(script, desired_file_ext=""):
    if len(desired_file_ext) == 0:
        file_extension = ""
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
        r'echo "${OVERRIDEN_CMD_ARGS[@]}"'
    )
    script.writelines(line + "\n" for line in body)

def make_script_hello_help():
    return "make_script_hello_help"



def get():
    scripts_generator = {
        "rag_add": make_script_rag_add,
        "rag_delete": make_script_rag_delete,
        "rag_list": make_script_rag_list,
        "ask_question": make_script_ask_question,
        "hello": make_script_hello
    }

    scripts_help_generator = {
        "rag_add": make_script_rag_add_help,
        "rag_delete": make_script_rag_delete_help,
        "rag_list": make_script_rag_list_help,
        "ask_question": make_script_ask_question_help,
        "hello": make_script_hello_help
    }
    return scripts_generator, scripts_help_generator
