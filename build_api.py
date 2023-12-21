#!/usr/bin/python

"""
Module is devoted to generate API to the docker container from existing API schemas.
API schemas is described in JSON format and mimic to the REST API guidelines

The only API is implemented at the moment is pseudo-filesystem providing interface
to the docker services.
"""

import argparse
import os
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

    fs_api_request = "\t".join([request_name, method_str, path_str, *params_list])
    return fs_api_request


parser = argparse.ArgumentParser(prog="Build API from schema directory")

parser.add_argument("directory", help="path where API schema located")

args = parser.parse_args()
directory = os.fsencode(args.directory)


for file in os.listdir(directory):
    request_filename = os.fsdecode(file)
    if not request_filename.endswith(".json"):
        continue

    api_file_path = os.path.join(os.fsdecode(directory), request_filename)
    with open(api_file_path, "r") as file:
        try:
            request = json.load(file)
            plain_request = transform_json_request_to_plain_request(
                request_filename.split(".")[0], request
            )
            print(plain_request)
        except json.decoder.JSONDecodeError as e:
            raise Exception(f"Error: {str(e)} in file: {api_file_path}")
