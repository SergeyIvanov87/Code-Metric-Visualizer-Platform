#!/usr/bin/python

import json
import os
from collections import defaultdict
import stat
import api_fs_args
import filesystem_utils

def get_context_type_ext_mapping():
    return {"image/apng":"apng",
               "application/epub+zip":"epub",
               "application/gzip":"gz",
               "application/json":"json",
               "application/msword":"doc",
               "application/octet-stream":"bin",
               "application/pdf":"pdg",
               "application/vnd.oasis.opendocument.spreadsheet":"ods",
               "application/vnd.openxmlformats-officedocument.wordprocessingml.document":"docx",
               "application/x-bzip":"bz",
               "application/x-bzip2":"bz2",
               "application/x-csh":"csh",
               "application/xml":"xml",
               "application/zip":"zip",

               "image/bmp":"bmp",
               "image/gif":"gif",
               "image/jpeg":"jpg",
               "image/png":"png",
               "image/svg+xml":"svg",
               "image/tiff":"tiff",

               "text/csv":"csv",
               "text/html":"html",
               "text/plain":"txt",
    }

def file_extension_from_content_type(content_type):
    mapping = get_context_type_ext_mapping()
    if content_type not in mapping.keys():
        raise KeyError(f"Content-Type: {content_type} is not found in the file extension mapping table")
    return mapping[content_type]

def file_extension_from_content_type_or_default(api_query, default):
    content_file_extension=""
    if "Content-Type" in api_query:
        content_file_extension = file_extension_from_content_type(api_query["Content-Type"])
    else:
        content_file_extension = default
    return content_file_extension


def content_type_from_file_extension(file_extension):
    content_type = ""
    for k, v in get_context_type_ext_mapping().items():
        if v == file_extension:
            content_type = k
            break

    if content_type == "":
        raise KeyError(f"The file extension: {file_extension} is not found in the Content-Type mapping table")
    return content_type


def compose_api_queries_pipe_names(api_mount_dir, query, session_id=""):
    method = query["Method"]
    query_str = query["Query"]
    params = query["Params"]


    # Content-Type is an optional field
    content_type=""
    if "Content-Type" in query:
        content_type = query["Content-Type"]

    if len(session_id) == 0:
        pipes = ("exec", "result" if content_type == "" else "result." + file_extension_from_content_type(content_type))
    else:
        pipes = ("exec", "result_" + session_id  if content_type == "" else "result." + file_extension_from_content_type(content_type) + "_" + session_id)
    pipes = [os.path.join(api_mount_dir, query_str, method, p) for p in pipes]
    return pipes



def deserialize_api_request_from_schema_file(api_request_schema_path):
    must_have_fields=["Method", "Query", "Params"]
    request = ""
    name = ""
    with open(api_request_schema_path, "r") as file:
        try:
            request = json.load(file)
            for f in must_have_fields:
                if f not in request:
                    raise ValueError(f"API schema must describe attribute: {f}. Check the schema in: {api_request_schema_path}")
            name = os.path.splitext(os.path.basename(api_request_schema_path))[0]
        except json.decoder.JSONDecodeError as e:
            raise Exception(f"Error: {str(e)} in file: {api_request_schema_path}")
    return name, request


def serialize_api_request_to_schema_file(api_request_schema_path, request):
    must_have_fields=["Method", "Query", "Params"]
    for f in must_have_fields:
        if f not in request:
            raise ValueError(f"API schema must describe attribute: {f}. Check the schema in: {request} before writing it in file: {api_request_schema_path}")
    tmp_file = api_request_schema_path + "_tmp"
    with open(tmp_file, "w") as file:
        try:
            json.dump(request, file)
        except Exception as e:
            try:
                os.remove(tmp_file)
            except Exception:
                pass
            raise Exception(f"Error: {str(e)} while writing in file: {tmp_file}")
    os.replace(tmp_file, api_request_schema_path)


def read_api_directory_content(path, directories_tree, arguments_for_directories, directories_for_markdown):
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
    directories_for_markdown.extend(filesystem_utils.read_files_from_path(path, '.*\\.md$'))
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
            output_pipe_file_extension=p_splitted[1].split('_')[0]  # multisessional API pipes has a suffix always
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


def gather_api_schemas_from_mount_point(mount_point, domain_name_api_entry):
    API_table = {}
    fs_tree = {}
    fs_args_tree = defaultdict(dict)
    directories_for_markdown = []

    # DFS starting from mount_point
    traverse_dirs_list = [os.path.join(mount_point, domain_name_api_entry)]
    while len(traverse_dirs_list) != 0:
        current_dir = traverse_dirs_list.pop()
        parsed_dirs, fs_tree, fs_args_tree, directories_for_markdown = read_api_directory_content(
            current_dir, fs_tree, fs_args_tree, directories_for_markdown
        )
        api_pipes = get_api_leaf_dir_pipes(current_dir)
        if len(api_pipes) >= 2 and len([p for p in api_pipes if os.path.basename(p) == "exec"]) == 1: # take into account multisessional output pipes. They number might be more than 2

            # it must be API leaf dir
            API_query_name, API_query = restore_api(current_dir, fs_tree, fs_args_tree, api_pipes, domain_name_api_entry)
            if API_query_name != "" and len(API_query) != 0:
                API_table[API_query_name] = API_query

        traverse_dirs_list.extend(parsed_dirs)
    return API_table, directories_for_markdown
