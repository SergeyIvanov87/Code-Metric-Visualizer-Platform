#!/usr/bin/python

"""
Generates `executor` script for API request serving
"""

import argparse
from argparse import RawTextHelpFormatter
from math import log10
import os
import pathlib
import sys
import stat

sys.path.append('modules')

import filesystem_utils

from api_fs_conventions import compose_api_exec_script_name
from api_fs_conventions import compose_api_fs_request_location_paths
from api_fs_conventions import get_generated_scripts_path
from api_fs_conventions import get_api_schema_files

from api_schema_utils import deserialize_api_request_from_schema_file
from api_schema_utils import file_extension_from_content_type
from api_schema_utils import file_extension_from_content_type_or_default

EMPTY_DEV_SCRIPT_MARK = "<TODO: THE SCRIPT IS EMPTY>"

def make_default_script(script):
    script.write(
        f"#!/bin/bash\n\nRESULT_FILE=${1}_result\n\n{EMPTY_DEV_SCRIPT_MARK}"
    )

def build_api_executors(api_schema_path, api_exec_generator_path, output_dir):
    # Load api generator module: put particular `api_exec_generator_path` at beginning
    # to prevent loading `api_generator` from main image dir
    sys.path.insert(0, api_exec_generator_path)
    import api_generator
    scripts_generator, _ = api_generator.get()

    generated_api_server_scripts_path = output_dir
    os.makedirs(generated_api_server_scripts_path, exist_ok=True)

    errors_detected = []
    schemas_file_list = get_api_schema_files(api_schema_path)
    for schema_file in schemas_file_list:
        req_name, request_data = deserialize_api_request_from_schema_file(schema_file)
        req_type = request_data["Method"]
        req_api = request_data["Query"]
        req_params = request_data["Params"]

        content_file_extension = file_extension_from_content_type_or_default(request_data, "")

        api_node, api_req_node = compose_api_fs_request_location_paths(
                "${SHARED_API_DIR}", req_api, req_type
        )



        """this builder must generate stub files for API request to implement"""
        """Must be done BEFORE docker image crafted"""
        try:
            script_name_generated = compose_api_exec_script_name(req_name)
            script_generated_path = os.path.join(generated_api_server_scripts_path, script_name_generated)

            with open(script_generated_path, "x") as script:
                filesystem_utils.make_file_executable(script_generated_path)
                if req_name in scripts_generator.keys():
                    scripts_generator[req_name](script, content_file_extension)
                elif hasattr(api_generator, 'generate_request_exec_script'):
                    api_generator.generate_request_exec_script(req_name, script, content_file_extension)
                else:
                    make_default_script(script)
        except FileExistsError as e:
            print(
                f'Skipping the script "{req_name}":\n\t"{e}"'
            )
            continue
        except Exception as e:
            errors_detected.append(str(e))
            continue

    if len(errors_detected) != 0:
        raise Exception(
            "Erros detected:\n{}\nScript execdir: {}".format(
                "\n".join(errors_detected), pathlib.Path(__file__).parent.resolve()
            )
        )




if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="Build file-system API nodes based on pseudo-REST API from cfg file",
        formatter_class=RawTextHelpFormatter,
    )

    parser.add_argument("api_root_dir", help="Path to the root directory incorporated JSON API schema descriptions")
    parser.add_argument("api_exec_generator", help="Path to a location of `api_generator.py`, which is responsible to generate the API-subset processing scripts")
    parser.add_argument("-o", "--output_dir",
                        help='Output directory where the generated scripts will be placed. Default=\"./{}\"'.format(get_generated_scripts_path()),
                        default=get_generated_scripts_path())
    args = parser.parse_args()


    build_api_executors(args.api_root_dir, args.api_exec_generator, args.output_dir)
