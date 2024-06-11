#!/usr/bin/python

import argparse
import json
import os
import stat
import sys

from collections import defaultdict

sys.path.append('modules')
sys.path.append(os.getenv("MAIN_IMAGE_ENV_SHARED_LOCATION_ENV", ""))

import api_fs_args
import filesystem_utils
from api_schema_utils import content_type_from_file_extension

# import api_fs_conventions


parser = argparse.ArgumentParser(
    prog="Traverse across file-system API nodes and restore API from it"
)

parser.add_argument("mount_point", help="A project location directory")
parser.add_argument("domain_name_api_entry", help="build API queries processor for that particular domain")
parser.add_argument(
    "output_api_dir", help="Path to the output directory with restored JSON API schemas"
)
args = parser.parse_args()


def read_directory_content(path, directories_tree, arguments_for_directories, directories_for_markdown):
    parsed_directories_list = {
        os.path.join(path, d)
        for d in os.listdir(path)
        if os.path.isdir(os.path.join(path, d))
    }
    local_directories_tree = {d: path for d in parsed_directories_list}
    if len(local_directories_tree) != 0:
        directories_tree.update(local_directories_tree)
    # parse files in directories which may represent arguments for FS API
    arguments_for_directories[path] = api_fs_args.read_args_dict(path)

    # search Markdown files
    directories_for_markdown.extend(filesystem_utils.read_files_from_path(path, '.*\.md$'))
    return parsed_directories_list, directories_tree, arguments_for_directories, directories_for_markdown


def get_api_leaf_dir_pipes(path):
    pipes_files = {
        f
        for f in os.listdir(path)
        if stat.S_ISFIFO(os.stat(os.path.join(path, f)).st_mode)
    }
    return pipes_files


def restore_api(leaf_dir, fs_tree, fs_args_tree, api_query_pipes, api_domain):
    supported_req_type = ["GET", "PUT", "POST"]
    req_type = os.path.basename(leaf_dir)
    if req_type not in supported_req_type:
        raise Exception(
            f"Incorrect API directory: {leaf_dir}. It must terminated by: {','.join(supported_req_type)}"
        )
    API_query = {}
    query_name = os.path.dirname(leaf_dir)
    domain_entry_pos = query_name.find(api_domain)
    if domain_entry_pos == -1:
        return "", API_query
    query_name = query_name[domain_entry_pos:]

    API_query["Method"] = req_type
    API_query["Query"] = query_name
    API_query["Params"] = {}

    # extract content-type from api pipes extension:
    output_pipe_file_extension=""
    for p in api_query_pipes:
        p_splitted = p.split(".")
        if len(p_splitted) == 2 and p_splitted[0].find("result") != -1:
            output_pipe_file_extension=p_splitted[1].split('_')[0]  # multisessional API pipes has suffix
            break
    if output_pipe_file_extension != "":
        API_query["Content-Type"] = content_type_from_file_extension(output_pipe_file_extension)

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
directories_for_markdown = []

# DFS starting from mount_point
traverse_dirs_list = [os.path.join(args.mount_point, args.domain_name_api_entry)]
while len(traverse_dirs_list) != 0:
    current_dir = traverse_dirs_list.pop()
    parsed_dirs, fs_tree, fs_args_tree, directories_for_markdown = read_directory_content(
        current_dir, fs_tree, fs_args_tree, directories_for_markdown
    )
    api_pipes = get_api_leaf_dir_pipes(current_dir)
    if len(api_pipes) >= 2: # take into account multisessional output pipes. They might be more than 2
        # it must be API leaf dir
        API_query_name, API_query = restore_api(current_dir, fs_tree, fs_args_tree, api_pipes, args.domain_name_api_entry)
        if API_query_name != "" and len(API_query) != 0:
            API_table[API_query_name] = API_query

    traverse_dirs_list.extend(parsed_dirs)

# unify *.md files content into single file
index_markdown_content = []
for md in set(directories_for_markdown):
    with open(md, "r") as md_file:
        index_markdown_content.extend(md_file.read().splitlines());

os.makedirs(args.output_api_dir, exist_ok=True)
for name, query in API_table.items():
    name = name + ".json"
    with open(os.path.join(args.output_api_dir, name), "w") as api_schema_file:
        json.dump(query, api_schema_file)
    query_url = query["Query"]

    # inject relative link onto HTTP query into markdown content
    for i in range(0, len(index_markdown_content)):
        if index_markdown_content[i].find("### " + query_url + "/" + query["Method"]) != -1:
            index_markdown_content[i] += f" [execute]({query_url})"

if len(directories_for_markdown) != 0:
    with open(os.path.join(args.output_api_dir, "index.md"), "w") as index_markdown:
        index_markdown.writelines(l + '\n' for l in index_markdown_content)
