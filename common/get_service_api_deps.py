#!/usr/bin/python

import argparse
import json
import os
import re
import stat
import sys

sys.path.append('modules')

from api_deps_utils import get_api_service_dependencies

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="Get dependency of the service on other services"
    )

    parser.add_argument("api_root_dir", help="Path to the root directory incorporated JSON API schema descriptions")
    parser.add_argument("--service", help="regex to filter an appropriate services out. Default='.*'", default=r'.*')
    args = parser.parse_args()

    print(json.dumps(get_api_service_dependencies(args.api_root_dir, args.service, r".*\.json$")))
