#!/usr/bin/python

import argparse
import os
import pathlib
import sys
import json

def transform_json_request_to_plain_request(request_name, req_json):
    method_str = str(req_json["Method"])
    path_str = str(req_json["Query"])
    params = req_json["Params"]
    params_list = []
    for p in params:
        # access only plain data
        if isinstance(params[p], str):
            params_list.append(str(p) + "=" + params[p])

    fs_api_request="\t".join([request_name, method_str, path_str, *params_list])
    return fs_api_request

parser = argparse.ArgumentParser(
    prog="Build API from schema directory"
)

parser.add_argument(
    "directory",
    help=f"path where API schema located"
)

args = parser.parse_args()
directory = os.fsencode(args.directory)


for file in os.listdir(directory):
    request_filename = os.fsdecode(file)
    if not request_filename.endswith(".json"):
        continue

    with open(os.path.join(os.fsdecode(directory), request_filename), "r") as file:
        request = json.load(file)
        plain_request = transform_json_request_to_plain_request(request_filename.split('.')[0], request)
        print(plain_request)
