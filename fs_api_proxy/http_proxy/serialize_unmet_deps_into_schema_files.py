#!/usr/bin/python

import argparse
import json
import os
import pathlib
import shutil
import sys
import stat

sys.path.append('modules')

from api_fs_conventions import get_api_schema_files

from api_schema_utils import deserialize_api_request_from_schema_file
from api_schema_utils import serialize_api_request_to_schema_file
import api_deps_utils


def canonize_internal_request(api_schema_file, service_full_name):
    req_name, request_data = deserialize_api_request_from_schema_file(api_schema_file)
    request_data["Query"] = api_deps_utils.canonize_relative_api_req(service_full_name, request_data["Query"])
    serialize_api_request_to_schema_file(api_schema_file, request_data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog=""
    )

    parser.add_argument("to_proxy", help="")
    parser.add_argument("serialize_path", help="", default = "to_proxy")
    args = parser.parse_args()

    if args.serialize_path == "":
        print("serialize_path cannot be empty. Abort")
        exit(255)

    shutil.rmtree(args.serialize_path, ignore_errors=True)

    service_queries_to_proxy = json.loads(args.to_proxy)
    print(f"service_queries_to_proxy: {service_queries_to_proxy}")
    for service, queries_to_proxy_list in service_queries_to_proxy.items():
        service_serialize_path=os.path.join(args.serialize_path, service)
        pathlib.Path(service_serialize_path).mkdir(parents=True, exist_ok=True)
        for query_name, request_data in queries_to_proxy_list.items():
            print(f"request_data: {request_data}")
            api_schema_file = os.path.join(service_serialize_path, query_name + ".json")
            serialize_api_request_to_schema_file(api_schema_file, request_data)
