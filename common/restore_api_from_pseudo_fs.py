#!/usr/bin/python

import argparse
import json
import os
import stat
import sys

sys.path.append('modules')
sys.path.append(os.getenv("MAIN_IMAGE_ENV_SHARED_LOCATION_ENV", ""))

import api_fs_args
import filesystem_utils
from api_schema_utils import gather_api_schemas_from_mount_point


parser = argparse.ArgumentParser(
    prog="Traverse across file-system API nodes and restore API from it"
)

parser.add_argument("mount_point", help="A project location directory")
parser.add_argument("domain_name_api_entry", help="build API queries processor for that particular domain")
parser.add_argument(
    "output_api_dir", help="Path to the output directory with restored JSON API schemas"
)
args = parser.parse_args()


API_table = {}
directories_for_markdown = []
API_table,directories_for_markdown = gather_api_schemas_from_mount_point(args.mount_point, args.domain_name_api_entry)

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
