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
from services_utils import build_and_launch_services
global_settings = Settings()



@pytest.fixture(scope="function", autouse=True)
def run_around_tests():
    # Tear up
    global global_settings

    shutil.rmtree(global_settings.api_dir, ignore_errors=True)
    generated_api_path = os.path.join(global_settings.work_dir, "generated")
    shutil.rmtree(generated_api_path, ignore_errors=True)
    os.mkdir(generated_api_path)

    servers = build_and_launch_services("/API", global_settings.work_dir, generated_api_path, global_settings.api_dir)
    yield servers

    print("Stop console servers", file=sys.stdout, flush=True)
    # Tear down
    # stop servers
    for s in servers:
        console_server.kill_detached(s)

    # avoid zombies
    for s in servers:
        s.wait(timeout=3)
