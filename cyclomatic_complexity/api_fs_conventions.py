#!/usr/bin/python

import json
import os
import stat
import filesystem_utils

def get_generated_scripts_path():
    return "services"


def get_api_hidden_node_name():
    return ".hid"

def api_gui_exec_filename_from_req_type(req_type):
    leaf_names = {"GET": get_api_hidden_node_name(), "PUT": "modify_this_file", "POST": "modify_this_file"}
    if req_type not in leaf_names.keys():
        print("Unsupported req_type: {req_type}. Default leaf node will be generated: api_file")
        return "api_file"
    return leaf_names[req_type]

def compose_api_gui_service_script_name(req_name):
    return f"{req_name}_listener.sh"

def compose_api_cli_service_script_name(req_name):
    return f"{req_name}_server.sh"

def compose_api_exec_script_name(req_name):
    return f"{req_name}_exec.sh"

def compose_api_help_script_name(req_name):
    return f"{req_name}_help.sh"


def get_api_gui_service_script_path(api_server_scripts_path_dir, req_name):
        return os.path.join(
            api_server_scripts_path_dir, compose_api_gui_service_script_name(req_name)
        )

def get_api_cli_service_script_path(api_server_scripts_path_dir, req_name):
        return os.path.join(
            api_server_scripts_path_dir, compose_api_cli_service_script_name(req_name)
        )

def compose_api_fs_request_location_paths(api_root, req, rtype):
    api_req_directory = os.path.join(api_root, req)
    api_exec_node_directory = os.path.join(api_req_directory, rtype)
    return api_req_directory, api_exec_node_directory


def get_api_schema_files(root_directory):
    directory_str = os.fsdecode(root_directory)
    return [os.path.join(directory_str, os.fsdecode(file)) for file in os.listdir(root_directory) if os.fsdecode(file).endswith(".json")]


def get_api_request_plain_params(req_param_json):
    params_list = []
    for p in req_param_json:
        # access only plain data
        if isinstance(req_param_json[p], str):
            params_list.append(str(p) + "=" + req_param_json[p])
    return params_list
