#!/usr/bin/env python3

import api_fs_exec_utils


def make_file_upload_script(script, desired_file_ext=""):
    extension = "." + desired_file_ext if desired_file_ext else ""
    body = (
        *api_fs_exec_utils.generate_exec_header(), "",
        *api_fs_exec_utils.generate_get_result_type(extension), "",
        *api_fs_exec_utils.generate_api_node_env_init(), "",
        *api_fs_exec_utils.generate_read_api_fs_args(), "",
        # API_NODE contains parameter files; deferred request artifacts belong in
        # the method directory beside exec/result so clients can discover them.
        'exec "${OPT_DIR}/deferred_query_launcher.py" --api-directory "${API_NODE}/POST" '
        '--processor "${WORK_DIR}/file_upload_processor.py" -- "${OVERRIDEN_CMD_ARGS[@]}"',
    )
    script.writelines(line + "\n" for line in body)


def get():
    return {"file_upload": make_file_upload_script}, {}
