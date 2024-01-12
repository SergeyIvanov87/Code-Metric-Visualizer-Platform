#!/usr/bin/python

import os
import stat
import filesystem_utils

def get_generated_scripts_path():
    return "services"


def get_api_hidden_node_name():
    return ".hid"

def get_api_leaf_node_name(req_type):
    leaf_names = {"GET": get_api_hidden_node_name(), "PUT": "modify_this_file", "POST": "modify_this_file"}
    if req_type not in leaf_names.keys():
        print("Unsupported req_type: {req_type}. Default leaf node will be generated: api_file")
        return "api_file"
    return leaf_names[req_type]

def compose_api_gui_service_script_name(req_name):
    return f"{req_name}_listener.sh"

def compose_api_cli_service_script_name(req_name):
    return f"{req_name}_server.sh"

def get_api_gui_service_script_path(req_name):
        return os.path.join(
            get_generated_scripts_path(), compose_api_gui_service_script_name(req_name)
        )

def get_api_cli_service_script_path(req_name):
        return os.path.join(
            get_generated_scripts_path(), compose_api_cli_service_script_name(req_name)
        )

def compose_api_exec_script_name(script_name):
    return f"{script_name}_exec.sh"

def compose_api_help_script_name(script_name):
    return f"{script_name}_help.sh"


def compose_api_fs_node_name(api_root, req, rtype):
    anode = os.path.join(api_root, req)
    areq_node = os.path.join(anode, rtype)
    return anode, areq_node
