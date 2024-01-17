#!/usr/bin/python

"""
This module gets an API file in text format previously generated from JSON schemna
README.md
"""

import argparse
from math import log10
import os
import pathlib
import sys
import stat
from collections import defaultdict

import filesystem_utils
from api_gen_utils import get_api_schema_files
from api_gen_utils import decode_api_request_from_schema_file


parser = argparse.ArgumentParser(
    prog="Build README from API JSON schema"
)

parser.add_argument("api_root_dir", help="Path to the root directory incorporated JSON API schema descriptions")
args = parser.parse_args()

schemas_file_list = get_api_schema_files(args.api_root_dir)
request_descriptions = defaultdict(list)
for schema_file in schemas_file_list:
    req_name, request_data = decode_api_request_from_schema_file(schema_file)
    if "Description" not in request_data:
        continue
    description_body = request_data["Description"]["body"]
    request_descriptions[req_name].append("## " + req_name)
    request_descriptions[req_name].append("### " + os.path.join(request_data["Query"], request_data["Method"]))
    if "header" not in request_data["Description"]:
        continue
    request_descriptions[req_name].append(request_data["Description"]["header"])
    request_descriptions[req_name].append("")

    if "body" not in request_data["Description"]:
        continue
    request_descriptions[req_name].append(request_data["Description"]["body"])
    request_descriptions[req_name].append("")

    if "footer" not in request_data["Description"]:
        continue
    request_descriptions[req_name].append(request_data["Description"]["footer"])

for key, value in request_descriptions.items():
    for row in value:
        print(f"{row}\n")
    print("\n\n")
