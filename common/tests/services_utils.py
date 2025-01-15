#!/usr/bin/python

import os
import shutil
import sys

import console_server
import filesystem_utils

from build_api_executors import build_api_executors
from build_api_services import build_api_services
from build_api_pseudo_fs import build_api_pseudo_fs


def build_services(service_schema_dirs, api_exec_generator_script_path, generated_api_path):

    build_api_executors(service_schema_dirs, api_exec_generator_script_path, generated_api_path)
    filesystem_utils.create_executable_file([generated_api_path], "req_cmd.sh", ["#!/usr/bin/env bash\n", "sleep 1\n"])

    generated_api_services_rel_path = "services"
    generated_api_services_path = os.path.join(
        generated_api_path, generated_api_services_rel_path
    )
    build_api_services(service_schema_dirs, generated_api_path, generated_api_services_path)
    server_scripts = [
        os.path.join(generated_api_services_path, f)
        for f in os.listdir(generated_api_services_path)
    ]
    return server_scripts


def build_and_launch_services(service_schema_dirs, api_exec_generator_script_path, generated_api_path, fs_api_root):
    server_scripts = build_services(service_schema_dirs, api_exec_generator_script_path, generated_api_path)
    assert len(server_scripts)

    print("Build pseudo-filesystem API", file=sys.stdout, flush=True)
    build_api_pseudo_fs(service_schema_dirs, fs_api_root)

    print("Launch console servers", file=sys.stdout, flush=True)
    server_env = os.environ.copy()
    server_env["WORK_DIR"] = generated_api_path
    servers = []
    for s in server_scripts:
        server = console_server.launch_detached(s, server_env, "")
        print(f"Launched server PID: {server.pid}, PGID : {os.getpgid(server.pid)}")
        servers.append(server)

    return servers
