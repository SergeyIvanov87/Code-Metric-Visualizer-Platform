#!/usr/bin/python

import os
import re
import stat

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
