#!/usr/bin/python

import api_fs_exec_utils
import api_fs_bash_utils


def make_script_rag_bulk_add(script, desired_file_ext=""):
    extension = "." + desired_file_ext if desired_file_ext else ""
    body = (
        *api_fs_exec_utils.generate_exec_header(), "",
        *api_fs_exec_utils.generate_get_result_type(extension), "",
        *api_fs_exec_utils.generate_api_node_env_init(), "",
        *api_fs_exec_utils.generate_read_api_fs_args(), "",
        'exec "${OPT_DIR}/deferred_query_launcher.py" --api-directory "${API_NODE}/POST" '
        '--processor "${WORK_DIR}/rag_bulk_add.py" -- "${OVERRIDEN_CMD_ARGS[@]}"',
    )
    script.writelines(line + "\n" for line in body)

"""
Provides a functions set which manages to generate API executor scripts
"""

def make_script_rag_add(script, desired_file_ext=""):
    extension = "." + desired_file_ext if desired_file_ext else ""
    body = (
        *api_fs_exec_utils.generate_exec_header(), "",
        *api_fs_exec_utils.generate_get_result_type(extension), "",
        *api_fs_exec_utils.generate_api_node_env_init(), "",
        *api_fs_exec_utils.generate_read_api_fs_args(), "",
        'SESSION_ID_VALUE="default"',
        'for arg in "${IN_SERVER_REQUEST_ARGS[@]}"; do',
        '  [[ "$arg" == SESSION_ID=* ]] && SESSION_ID_VALUE="${arg#SESSION_ID=}"',
        'done',
        'declare -a RAG_ARGS=()',
        'document_data=""',
        'for ((i=0; i<${#OVERRIDEN_CMD_ARGS[@]}; i+=2)); do',
        '  name="${OVERRIDEN_CMD_ARGS[i]}"',
        '  value="${OVERRIDEN_CMD_ARGS[i+1]}"',
        '  case "$name" in',
        '    doc_data) document_data="$value" ;;',
        '    -URI) [[ -z "$value" ]] || RAG_ARGS+=("$name" "$value") ;;',
        '    -metadata|-doc_type) RAG_ARGS+=("$name" "$value") ;;',
        '  esac',
        'done',
        'printf "%s" "$document_data" | "${WORK_DIR}/rag_add.py" '
        '--session_id="${SESSION_ID_VALUE}" -db_host="${VECTOR_DB_HOST}" '
        '-db_port="${VECTOR_DB_PORT}" "${RAG_ARGS[@]}" '
        '"${SHARED_API_DIR}" "${MAIN_SERVICE_NAME}"',
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
        r'${WORK_DIR}/rag_delete.py "${OVERRIDEN_CMD_ARGS[@]}" --session_id="${SESSION_ID_VALUE}" -db_host="${VECTOR_DB_HOST}" -db_port="${VECTOR_DB_PORT}" "${SHARED_API_DIR}" "${MAIN_SERVICE_NAME}"'
    )
    script.writelines(line + "\n" for line in body)

def make_script_rag_delete_help():
    return "make_script_rag_delete_help"


def make_script_rag_get_docs(script, desired_file_ext=""):
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
        r'echo "${OVERRIDEN_CMD_ARGS[@]}" | xargs ${WORK_DIR}/rag_get_docs.py --session_id="${SESSION_ID_VALUE}" ${SHARED_API_DIR} ${MAIN_SERVICE_NAME}'
    )
    script.writelines(line + "\n" for line in body)


def make_script_rag_get_docs_help():
    return "make_script_rag_get_docs_help"


def make_script_rag_sync(script, desired_file_ext=""):
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
        r'${WORK_DIR}/rag_sync.py "${OVERRIDEN_CMD_ARGS[@]}" --session_id="${SESSION_ID_VALUE}" -db_host="${VECTOR_DB_HOST}" -db_port="${VECTOR_DB_PORT}" "${SHARED_API_DIR}" "${MAIN_SERVICE_NAME}"'
    )
    script.writelines(line + "\n" for line in body)


def make_script_rag_sync_help():
    return "make_script_rag_sync_help"


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
        "rag_add": make_script_rag_add,
        "rag_bulk_add": make_script_rag_bulk_add,
        "rag_delete": make_script_rag_delete,
        "rag_get_docs": make_script_rag_get_docs,
        "rag_sync": make_script_rag_sync,
        "chat": make_script_chat
    }

    scripts_help_generator = {
        "rag_add": make_script_rag_add_help,
        "rag_delete": make_script_rag_delete_help,
        "rag_get_docs": make_script_rag_get_docs_help,
        "rag_sync": make_script_rag_sync_help,
        "chat": make_script_chat_help
    }
    return scripts_generator, scripts_help_generator
