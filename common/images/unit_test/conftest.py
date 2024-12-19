#!/usr/bin/python

import os
import pathlib
import pytest
import stat
import shutil
import sys
import time

import console_server
import ut_utils

from settings import Settings
from build_api_executors import build_api_executors
from build_api_services import build_api_services
from build_api_pseudo_fs import build_api_pseudo_fs

global_settings = Settings()


def build_and_launch_services(service_schema_dirs, generated_api_scripts_dir, fs_api_root):
    generated_api_rel_path = "generated"
    generated_api_path = os.path.join(generated_api_scripts_dir, generated_api_rel_path)
    shutil.rmtree(generated_api_path, ignore_errors=True)
    os.mkdir(generated_api_path)

    build_api_executors(service_schema_dirs, generated_api_scripts_dir, generated_api_path)
    ut_utils.create_executable_file([generated_api_path], "req_cmd.sh", ["#!/usr/bin/env bash\n", "sleep 1\n"])

    generated_api_services_rel_path = "services"
    generated_api_services_path = os.path.join(
        generated_api_path, generated_api_services_rel_path
    )
    build_api_services(service_schema_dirs, generated_api_path, generated_api_services_path)
    server_scripts = [
        os.path.join(generated_api_services_path, f)
        for f in os.listdir(generated_api_services_path)
    ]
    assert len(server_scripts)

    print("Build pseudo-filesystem API", file=sys.stdout, flush=True)
    generated_api_mount_point = fs_api_root
    shutil.rmtree(generated_api_mount_point, ignore_errors=True)
    build_api_pseudo_fs(service_schema_dirs, generated_api_mount_point)

    print("Launch console servers", file=sys.stdout, flush=True)
    server_env = os.environ.copy()
    server_env["WORK_DIR"] = generated_api_path
    servers = []
    for s in server_scripts:
        server = console_server.launch_detached(s, server_env, "")
        print(f"Launched server PID: {server.pid}, PGID : {os.getpgid(server.pid)}")
        servers.append(server)

    return servers


@pytest.fixture(scope="function", autouse=True)
def run_around_tests():
    # Tear up
    global global_settings
    servers =vbuild_and_launch_services("/API", global_settings.work_dir, global_settings.api_dir)
    yield servers

    print("Stop console servers", file=sys.stdout, flush=True)
    # Tear down
    # stop servers
    for s in servers:
        console_server.kill_detached(s)

    # avoid zombies
    for s in servers:
        s.wait(timeout=3)
