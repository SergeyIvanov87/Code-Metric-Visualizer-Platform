#!/usr/bin/python

import argparse
import json
import os
import re
import stat

from api_schema_utils import compose_api_queries_pipe_names
from api_schema_utils import deserialize_api_request_from_schema_file


def canonize_relative_api_req(full_service_name, common_api_req):
    return os.path.join(full_service_name, common_api_req.removeprefix("+/")) if common_api_req.startswith("+/") else common_api_req

def get_api_service_dependency_files(api_schemas_input_dir, file_match_regex = r".*\.json$"):
    services_dependencies = {}
    p = re.compile(file_match_regex)
    main_root = os.path.basename(api_schemas_input_dir)
    for root, services, files in os.walk(os.path.join(api_schemas_input_dir)):
        if main_root == os.path.basename(root):
            for s in services:
                services_dependencies[os.path.join(root, s)] = list()
        if root in services_dependencies.keys():
            services_dependencies[root] = [os.path.join(root, f) for f in files if p.match(f)]
    return services_dependencies



def get_api_service_dependency_files(api_schemas_input_dir, service_regex = r".*", file_match_regex = r".*\.json$"):
    services_dependencies = {}
    p = re.compile(file_match_regex)
    sg = re.compile(service_regex)
    main_root = os.path.basename(api_schemas_input_dir)
    for root, services, files in os.walk(os.path.join(api_schemas_input_dir)):
        if main_root == os.path.basename(root):
            for s in services:
                if sg.match(s) or s == service_regex:
                    services_dependencies[os.path.join(root, s)] = list()
        if root in services_dependencies.keys():
            services_dependencies[root] = [os.path.join(root, f) for f in files if p.match(f)]
    return services_dependencies

def get_api_service_dependencies(api_schemas_input_dir, service_regex = r".*", file_match_regex = r".*\.json$"):
    services_schema_files = get_api_service_dependency_files(api_schemas_input_dir, service_regex, file_match_regex)
    service_dependencies = dict()
    for service_path, service_dep_files in services_schema_files.items():
        service_name = os.path.basename(service_path)
        service_dependencies[service_name] = dict()
        for file in service_dep_files:
            req_name, req_data = deserialize_api_request_from_schema_file(file)
            service_dependencies[service_name][req_name] = req_data

    return service_dependencies

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="Get dependency of the service on other services"
    )

    parser.add_argument("api_root_dir", help="Path to the root directory incorporated JSON API schema descriptions")
    parser.add_argument("--service", help="regex to filter an appropriate services out. Default='.*'", default=r'.*')
    args = parser.parse_args()

    print(json.dumps(get_api_service_dependencies(args.api_root_dir, args.service, r".*\.json$")))
