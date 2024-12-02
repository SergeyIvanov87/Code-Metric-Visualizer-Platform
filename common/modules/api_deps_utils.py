#!/usr/bin/python

import argparse
import os
import re
import stat

from api_schema_utils import compose_api_queries_pipe_names

def get_api_service_deps(api_schemas_input_dir, file_match_regex = r".*\.json$"):
    services_dependencies = {}
    p = re.compile(file_match_regex)
    for root, services, files in os.walk(os.path.join(api_schemas_input_dir)):
        if os.path.basename(root) == "deps":
            for s in services:
                services_dependencies[os.path.join(root, s)] = list()
        if root in services_dependencies.keys():
            services_dependencies[root] = [os.path.join(root, f) for f in files if p.match(f)]
    return services_dependencies



def get_api_service_deps(api_schemas_input_dir, service_regex = r".*", file_match_regex = r".*\.json$"):
    services_dependencies = {}
    p = re.compile(file_match_regex)
    sg = re.compile(service_regex)
    for root, services, files in os.walk(os.path.join(api_schemas_input_dir)):
        if os.path.basename(root) == "deps":
            for s in services:
                if sg.match(s) or s == service_regex:
                    services_dependencies[os.path.join(root, s)] = list()
        if root in services_dependencies.keys():
            services_dependencies[root] = [os.path.join(root, f) for f in files if p.match(f)]
    return services_dependencies


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="Get dependency of the service on other services"
    )

    parser.add_argument("api_root_dir", help="Path to the root directory incorporated JSON API schema descriptions")
    parser.add_argument("--service", help="regex to filter an appropriate services out. Default='.*'", default=r'.*')
    args = parser.parse_args()

    print(get_api_service_deps(args.api_root_dir, args.service, r".*\.json$"))
