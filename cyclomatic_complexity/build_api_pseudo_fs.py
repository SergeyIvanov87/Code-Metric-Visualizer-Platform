#!/usr/bin/python

"""
The module generates pseudo-filesystem which is used as API service entrance points.
Each API request represented by a file node `exec` located in the pseudo-filesystem by
a path mirrored as a REST query path. Parameters of the API request are enumerated as files
placed on the same path as well. In order to change the request parameter values,
just open the file representing the parameter and change related value. Do not forget to save it.

API request will be executed when designated `inotify` event is recognized by
an appropriate API `service` script. Speaking about a simple GET query, it is
a read-operation of a file `exec` resided by relevant API path. Such operation may be
triggered by a simple `echo` command or (!) by just opening GET directory in your
favourable File Manager.
"""

import argparse
import os
import pathlib
import stat
import sys

import filesystem_utils

from api_fs_conventions import compose_api_fs_request_location_paths
from api_fs_conventions import api_gui_exec_filename_from_req_type
from api_fs_conventions import get_api_schema_files
from api_fs_conventions import get_api_request_plain_params

from api_schema_utils import deserialize_api_request_from_schema_file

from api_fs_args import write_args

parser = argparse.ArgumentParser(
    prog="Build file-system API nodes based on pseudo-REST API from cfg file"
)

parser.add_argument("api_root_dir", help="Path to the root directory incorporated JSON API schema descriptions")
parser.add_argument("mount_point", help="destination to build file-system nodes")
args = parser.parse_args()


def create_api_fs_node(api_root_path, req, rtype, rparams):
    api_req_directory, api_exec_node_directory = compose_api_fs_request_location_paths(api_root_path, req, rtype)
    os.makedirs(api_exec_node_directory, exist_ok=True)
    filesystem_utils.append_file_list_mode(
                [api_req_directory, api_exec_node_directory],
                stat.S_IWUSR
                | stat.S_IRUSR
                | stat.S_IWGRP
                | stat.S_IRGRP
                | stat.S_IWOTH
                | stat.S_IROTH
    )

    api_gui_exec_filename = os.path.join(api_exec_node_directory, api_gui_exec_filename_from_req_type(rtype))

    with open(api_gui_exec_filename, "w") as api_exec_file:
        if rtype == "GET":
            filesystem_utils.make_file_executable(api_gui_exec_filename)
        else:
            filesystem_utils.append_file_mode(
                api_gui_exec_filename,
                stat.S_IWUSR
                | stat.S_IRUSR
                | stat.S_IWGRP
                | stat.S_IRGRP
                | stat.S_IWOTH
                | stat.S_IROTH,
            )

        api_exec_file.write(
            "0\n"
        )  # event `access` in notify can't be trigger on empty file

    # create params as files
    write_args(api_req_directory, rparams)
    return api_req_directory, api_exec_node_directory

schemas_file_list = get_api_schema_files(args.api_root_dir)
for schema_file in schemas_file_list:
    req_name, request_data = deserialize_api_request_from_schema_file(schema_file)
    req_type = request_data["Method"]
    req_api = request_data["Query"]
    req_params = get_api_request_plain_params(request_data["Params"])

    """re-create pseudo-filesystem directory structure based on API query"""
    create_api_fs_node(args.mount_point, req_api, req_type, req_params)
