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

from math import log10

import filesystem_utils

from api_gen_utils import compose_api_fs_node_name
from api_gen_utils import get_api_leaf_node_name

def create_api_fs_node(api_root, req, rtype, rparams):
    api_node, api_req_node = compose_api_fs_node_name(api_root, req, rtype)
    os.makedirs(api_req_node, exist_ok=True)
    filesystem_utils.append_file_list_mode(
                [api_node, api_req_node],
                stat.S_IWUSR
                | stat.S_IRUSR
                | stat.S_IWGRP
                | stat.S_IRGRP
                | stat.S_IWOTH
                | stat.S_IROTH
    )

    api_node_leaf = os.path.join(api_req_node, get_api_leaf_node_name(rtype))

    with open(api_node_leaf, "w") as api_leaf_file:
        if rtype == "GET":
            filesystem_utils.make_file_executable(api_node_leaf)
        else:
            filesystem_utils.append_file_mode(
                api_node_leaf,
                stat.S_IWUSR
                | stat.S_IRUSR
                | stat.S_IWGRP
                | stat.S_IRGRP
                | stat.S_IWOTH
                | stat.S_IROTH,
            )

        api_leaf_file.write(
            "0\n"
        )  # event `access` in notify can't be trigger on empty file

    # create params as files
    counter = 0
    params_count = len(rparams)
    if params_count != 0:
        params_10based = int(log10(params_count)) + 1
        # put a leading zero as we need to get ordered params list
        param_digit_format = "{:0" + str(params_10based) + "d}"
        for param in rparams:
            param_name, param_value = param.split("=")
            param_name_path = os.path.join(api_node, param_digit_format.format(counter) + "." + param_name)
            counter += 1

            with open(param_name_path, "w") as api_file_param:
                api_file_param.write(param_value)
                filesystem_utils.append_file_mode(
                    param_name_path,
                    stat.S_IWUSR
                    | stat.S_IRUSR
                    | stat.S_IWGRP
                    | stat.S_IRGRP
                    | stat.S_IWOTH
                    | stat.S_IROTH,
                )

    return api_node, api_req_node

parser = argparse.ArgumentParser(
    prog="Build file-system API nodes based on pseudo-REST API from cfg file"
)

parser.add_argument("api_file", help="Path to file with API description")
parser.add_argument("mount_point", help="destination to build file-system nodes")
args = parser.parse_args()

with open(args.api_file, "r") as api_file:
    for request_line in api_file:
        request_params = [s.strip() for s in request_line.split("\t")]
        if len(request_params) < 3:
            continue

        (req_name, req_type, req_api, *req_params) = request_params
        """re-create pseudo-filesystem directory structure based on API query"""
        create_api_fs_node(args.mount_point, req_api, req_type, req_params)
