#!/usr/bin/python

import api_fs_bash_utils
import api_fs_exec_utils


def _make_json_mock(script, query_name, desired_file_ext="", stdin_parameter=None):
    file_extension = f".{desired_file_ext}" if desired_file_ext else ".json"
    body = [
        *api_fs_exec_utils.generate_exec_header(),
        "",
        *api_fs_exec_utils.generate_get_result_type(file_extension),
        "",
        *api_fs_exec_utils.generate_api_node_env_init(),
        "",
        'SESSION_ID_VALUE=""',
        'for arg in "${IN_SERVER_REQUEST_ARGS[@]}"; do',
        '  [[ "$arg" == SESSION_ID=* ]] && SESSION_ID_VALUE="${arg#SESSION_ID=}"',
        "done",
        "",
        *api_fs_exec_utils.generate_read_api_fs_args(
            preserve_empty_named_values=True
        ),
        "",
    ]
    if stdin_parameter is None:
        body.append(
            f'"${{WORK_DIR}}/mock_exec/{query_name}.py" '
            'SESSION_ID "${SESSION_ID_VALUE}" "${OVERRIDEN_CMD_ARGS[@]}"'
        )
    else:
        body.extend(
            [
                "declare -a MOCK_ARGS=()",
                'stdin_value=""',
                'for ((i=0; i<${#OVERRIDEN_CMD_ARGS[@]}; i+=2)); do',
                f'  if [[ "${{OVERRIDEN_CMD_ARGS[i]}}" == {stdin_parameter} ]]; then',
                '    stdin_value="${OVERRIDEN_CMD_ARGS[i+1]}"',
                "  else",
                '    MOCK_ARGS+=("${OVERRIDEN_CMD_ARGS[i]}" '
                '"${OVERRIDEN_CMD_ARGS[i+1]}")',
                "  fi",
                "done",
                f'printf "%s" "$stdin_value" | '
                f'"${{WORK_DIR}}/mock_exec/{query_name}.py" '
                'SESSION_ID "${SESSION_ID_VALUE}" "${MOCK_ARGS[@]}"',
            ]
        )
    script.writelines(line + "\n" for line in body)


def make_rag_add(script, desired_file_ext=""):
    _make_json_mock(script, "rag_add", desired_file_ext)


def make_rag_add_data(script, desired_file_ext=""):
    _make_json_mock(script, "rag_add_data", desired_file_ext, "doc_data")


def make_rag_bulk_add(script, desired_file_ext=""):
    file_extension = f".{desired_file_ext}" if desired_file_ext else ".json"
    body = (
        *api_fs_exec_utils.generate_exec_header(),
        "",
        *api_fs_exec_utils.generate_get_result_type(file_extension),
        "",
        *api_fs_exec_utils.generate_api_node_env_init(),
        "",
        *api_fs_exec_utils.generate_read_api_fs_args(
            preserve_empty_named_values=True
        ),
        "",
        'exec "${UTILS}/deferred_query_launcher.py" '
        '--api-directory "${API_NODE}/POST" '
        '--processor "${WORK_DIR}/mock_exec/rag_bulk_add.py" -- '
        '"${OVERRIDEN_CMD_ARGS[@]}"',
    )
    script.writelines(line + "\n" for line in body)


def make_rag_delete(script, desired_file_ext=""):
    _make_json_mock(script, "rag_delete", desired_file_ext)


def make_rag_get_docs(script, desired_file_ext=""):
    _make_json_mock(script, "rag_get_docs", desired_file_ext)


def make_rag_sync(script, desired_file_ext=""):
    _make_json_mock(script, "rag_sync", desired_file_ext)


def make_read_id(script, desired_file_ext=""):
    file_extension = f".{desired_file_ext}" if desired_file_ext else ".json"
    body = (
        *api_fs_exec_utils.generate_exec_header(),
        "",
        *api_fs_bash_utils.generate_extract_attr_value_from_string(),
        "",
        *api_fs_bash_utils.generate_add_suffix_if_exist(),
        "",
        *api_fs_bash_utils.generate_wait_until_pipe_exist(),
        "",
        *api_fs_exec_utils.generate_get_result_type(file_extension),
        "",
        *api_fs_exec_utils.generate_api_node_env_init(),
        "",
        api_fs_bash_utils.extract_attr_value_from_string()
        + ' "SESSION_ID" "${2}" "" \'=\' SESSION_ID_VALUE',
        "",
        *api_fs_exec_utils.generate_read_api_fs_args(),
        "",
        '"${WORK_DIR}/mock_exec/read_id.py" SESSION_ID "${SESSION_ID_VALUE}" '
        '"${OVERRIDEN_CMD_ARGS[@]}"',
    )
    script.writelines(line + "\n" for line in body)


def make_read_id_help():
    return "make_read_id_help"


def make_mock_help():
    return "functional dependency mock"


def get():
    scripts_generator = {
        "rag_add": make_rag_add,
        "rag_add_data": make_rag_add_data,
        "rag_bulk_add": make_rag_bulk_add,
        "rag_delete": make_rag_delete,
        "rag_get_docs": make_rag_get_docs,
        "rag_sync": make_rag_sync,
        "read_id": make_read_id,
    }
    scripts_help_generator = {
        query_name: make_mock_help for query_name in scripts_generator
    }
    scripts_help_generator["read_id"] = make_read_id_help
    return scripts_generator, scripts_help_generator
