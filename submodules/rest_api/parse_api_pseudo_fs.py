#!/usr/bin/python

import argparse
import json
import os
import stat
import sys

from collections import defaultdict

sys.path.append(os.getenv("MAIN_IMAGE_ENV_SHARED_LOCATION_ENV", ""))
import read_api_fs_args

# import filesystem_utils
# import api_gen_utils


parser = argparse.ArgumentParser(
    prog="Traverse across file-system API nodes and restore API from it"
)

parser.add_argument("mount_point", help="An existing mounted pseudo fs root node path")
parser.add_argument(
    "output_api_dir", help="Path to the output directory with restored JSON API schemas"
)
args = parser.parse_args()


def read_directory_content(path, directories_tree, arguments_for_directories):
    parsed_directories_list = {
        os.path.join(path, d)
        for d in os.listdir(path)
        if os.path.isdir(os.path.join(path, d))
    }
    local_directories_tree = {d: path for d in parsed_directories_list}
    if len(local_directories_tree) != 0:
        directories_tree.update(local_directories_tree)
    arguments_for_directories[path] = read_api_fs_args.read_args_dict(path)
    return parsed_directories_list, directories_tree, arguments_for_directories


def is_api_leaf_dir(path):
    pipes_files = {
        f
        for f in os.listdir(path)
        if stat.S_ISFIFO(os.stat(os.path.join(path, f)).st_mode)
    }
    return len(pipes_files) == 2


def restore_api(leaf_dir, fs_tree, fs_args_tree):
    supported_req_type = ["GET", "PUT", "POST"]
    req_type = os.path.basename(leaf_dir)
    if req_type not in supported_req_type:
        raise Exception(
            f"Incorrect API directory: {leaf_dir}. It must terminated by: {','.join(supported_req_type)}"
        )
    API_query = {}
    API_query["Method"] = req_type
    API_query["Query"] = os.path.dirname(leaf_dir)
    API_query["Params"] = {}
    api_params = API_query
    api_params_ref = None
    api_parent_dir = os.path.dirname(leaf_dir)
    while api_parent_dir in fs_tree.keys():
        if len(fs_args_tree[api_parent_dir]) != 0:
            api_params["Params"] = {}
            api_params_ref = api_params
            api_params = api_params["Params"]
            for n, v in fs_args_tree[api_parent_dir].items():
                api_params[n] = v
        api_parent_dir = fs_tree[api_parent_dir]
        api_params[api_parent_dir] = {}
        api_params_ref = api_params
        api_params = api_params[api_parent_dir]

    if len(api_params) == 0:
        del api_params_ref[api_parent_dir]
    return API_query["Query"].replace(os.sep, "_"), API_query


API_table = {}
fs_tree = {}
fs_args_tree = defaultdict(dict)
traverse_dirs_list = [args.mount_point]
while len(traverse_dirs_list) != 0:
    current_dir = traverse_dirs_list.pop()
    parsed_dirs, fs_tree, fs_args_tree = read_directory_content(
        current_dir, fs_tree, fs_args_tree
    )
    if is_api_leaf_dir(current_dir):
        API_query_name, API_query = restore_api(current_dir, fs_tree, fs_args_tree)
        API_table[API_query_name] = API_query

    traverse_dirs_list.extend(parsed_dirs)


os.makedirs(args.output_api_dir, exist_ok=True)
for name, query in API_table.items():
    name = name + ".json"
    with open(os.path.join(args.output_api_dir, name), "w") as api_schema_file:
        json.dump(query, api_schema_file)
