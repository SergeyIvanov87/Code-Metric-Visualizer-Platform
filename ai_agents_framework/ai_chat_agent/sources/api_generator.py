#!/usr/bin/python

import api_fs_exec_utils
import api_fs_bash_utils

def make_script_chat(script, desired_file_ext=""):
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
        r'${WORK_DIR}/agentic_rag.py "${OVERRIDEN_CMD_ARGS[@]}" --session_id="${SESSION_ID_VALUE}" -db_host="${VECTOR_DB_HOST}" -db_port="${VECTOR_DB_PORT}" "${SHARED_API_DIR}" "${MAIN_SERVICE_NAME}" "${ASSET_MODELS}"'
    )
    script.writelines(line + "\n" for line in body)

def make_script_chat_help():
    return "make_chat_help"



def get():
    scripts_generator = {
        "chat": make_script_chat
    }

    scripts_help_generator = {
        "chat": make_script_chat_help
    }
    return scripts_generator, scripts_help_generator
