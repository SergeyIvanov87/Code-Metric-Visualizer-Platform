#!/usr/bin/python

import argparse
import os
import pathlib
import stat
import sys

from collections import defaultdict

sys.path.append(os.getenv('MAIN_IMAGE_ENV_SHARED_LOCATION_ENV', ''))
import read_api_fs_args
#import filesystem_utils
#import api_gen_utils


parser = argparse.ArgumentParser(
    prog="Traverse across file-system API nodes and restore API from it"
)

parser.add_argument("mount_point", help="An existing mounted pseudo fs root node path")
parser.add_argument("output_api_dir", help="Path to the output directory with restored JSON API schemas")
args = parser.parse_args()


def read_directory_content(path, directories_tree, arguments_for_directories):
    parsed_directories_list = {os.path.join(path, d) for d in os.listdir(path) if os.path.isdir(os.path.join(path,d))}
    local_directories_tree = {d: path for d in parsed_directories_list}
    if len(local_directories_tree) != 0:
        directories_tree.update(local_directories_tree)
    arguments_for_directories[path] = read_api_fs_args.read_args_dict(path)
    return parsed_directories_list, directories_tree, arguments_for_directories

def is_api_leaf_dir(path):
    pipes_files = {f for f in os.listdir(path) if stat.S_ISFIFO(os.stat(os.path.join(path, f)).st_mode)}
    print(f"pipes in leaf {pipes_files}")
    return len(pipes_files) == 2


def restore_api(leaf_dir, fs_tree, fs_args_tree):
    print(f"restore api: {leaf_dir}")
    supported_req_type = ["GET", "PUT", "POST"]
    req_type = os.path.basename(leaf_dir)
    if req_type not in supported_req_type:
        raise Exception(f"Incorrect API directory: {leaf_dir}. It must terminated by: {','.join(supported_req_type)}")
    API_query = {}
    API_query["Method"] = req_type
    API_query["Query"] = os.path.dirname(leaf_dir)
    API_query["Params"] = {}
    api_params = API_query["Params"]
    api_parent_dir = leaf_dir
    while api_parent_dir in fs_tree.keys():
        for n, v in fs_args_tree[api_parent_dir].items():
            api_params[n] = v
        api_parent_dir = fs_tree[api_parent_dir]
        api_params[os.path.dirname(api_parent_dir)] = {"Params":{}}
        api_params = api_params[os.path.dirname(api_parent_dir)]["Params"]
    return API_query

API_table = []
fs_tree = {}
fs_args_tree = defaultdict(dict)
traverse_dirs_list = [args.mount_point]
while len(traverse_dirs_list) != 0:
    current_dir = traverse_dirs_list.pop()
    parsed_dirs, fs_tree, fs_args_tree = read_directory_content(current_dir, fs_tree, fs_args_tree)
    if is_api_leaf_dir(current_dir):
        API_query = restore_api(current_dir, fs_tree, fs_args_tree)
        print(API_query)
        API_table.append(API_query)

    traverse_dirs_list.extend(parsed_dirs)



'''
"Method" : "GET",
    "Query": "api.pmccabe_collector.restapi.org/cc/statistic/view/flamegraph",
    "Params": {
        "view" : {
            "statistic" : {
                "watch_list" : {
                    "-regex": "\".*\\.\\(hpp\\|cpp\\|c\\|h\\)\"",
                    "-prune": "! -path \"*buil*\" ! -path \"*thirdpart*\""
                },
                "-mmcc" : "1,",
                "-tmcc" : "1,",
                "-sif" : "1,",
                "-lif" : "1,"
            },
            "-attr" : "mmcc,tmcc,sif,lif"
        },
        "--width": "1200",
        "--height" : "16"
    },
    "Description": {
        "header": "Generates visual representation of various cyclomatic compexity metrics of the project in the flamegraph format.\nFor more information about flamegraph, please refer https://github.com/brendangregg/FlameGraph#3-flamegraphpl",
        "body": "To make a query:\n\n`echo \"0\" > api.pmccabe_collector.restapi.org/cc/statistic/view/flamegraph/GET/exec`\n\nTo wait and extract the query result:\n\n`cat api.pmccabe_collector.restapi.org/cc/statistic/view/flamegraph/GET/result.svg > <your_filename>.svg`\n\n",
        "footer": "Please pay attention that a flamegraph collected in `*.svg` format is interactive in exploration. To leverage that navigation through a call stack please open this file in any web-browser."
    }
'''
