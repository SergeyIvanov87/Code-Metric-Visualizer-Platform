#!/usr/bin/python

import os
import pathlib
import pytest
import signal
import socket
import stat
import sys
import time
import ut_utils

from settings import Settings
from utils import get_api_queries
from utils import compose_api_queries_pipe_names
from async_executor import AsyncExecutor
from api_fs_query import APIQuery
from renew_pseudo_fs_pipes import remove_api_fs_pipes_node

global_settings = Settings()
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())


@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_graceful_shutdown_pipes(name, query, run_around_tests):
    global global_settings
    print(f"Test start: {name}", file=sys.stdout, flush=True)

    # compose expected pipe names, based on query data
    communication_pipes = compose_api_queries_pipe_names(global_settings.api_dir, query)
    # pipes exist
    print(f"Check base API pipes: {communication_pipes}", file=sys.stdout, flush=True)
    for p in communication_pipes:
        api_result_pipe_timeout_cycles = 0
        while not (os.path.exists(p) and stat.S_ISFIFO(os.stat(p).st_mode)):
            time.sleep(0.1)
            api_result_pipe_timeout_cycles += 1
            assert api_result_pipe_timeout_cycles <= 30

    # trigger result pipes waiting
    generated_api_rel_path = "generated"
    ut_utils.create_executable_file([global_settings.work_dir, generated_api_rel_path], "req_cmd.sh", ["#!/usr/bin/env bash\n", "sleep infinity &\n", "wait $!"])
    executors = []
    session_id = 0
    executor = ut_utils.APIExecutor(global_settings.api_dir, query, session_id)
    executor.run(session_id)
    executors.append(executor)

    # TODO wait for some event designated to reflect that thread have started and wait for an answer
    time.sleep(5)
    req_type = query["Method"]
    req_api = query["Query"]
    deleted_files = remove_api_fs_pipes_node(global_settings.api_dir, query["Query"], query["Method"])
    assert len(deleted_files)

    print("waiting threads must be unblocked")
    for e in executors:
        e.join()


    # pipes do not exist
    for p in communication_pipes:
        assert not os.path.exists(p)


@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_graceful_shutdown_processes(name, query, run_around_tests):
    global global_settings
    print(f"Test start: {name}", file=sys.stdout, flush=True)

    # compose expected pipe names, based on query data
    communication_pipes = compose_api_queries_pipe_names(global_settings.api_dir, query)
    # pipes exist
    print(f"Check base API pipes: {communication_pipes}", file=sys.stdout, flush=True)
    for p in communication_pipes:
        api_result_pipe_timeout_cycles = 0
        while not (os.path.exists(p) and stat.S_ISFIFO(os.stat(p).st_mode)):
            time.sleep(0.1)
            api_result_pipe_timeout_cycles += 1
            assert api_result_pipe_timeout_cycles <= 30

    generated_api_rel_path = "generated"
    ut_utils.create_executable_file([global_settings.work_dir, generated_api_rel_path], "req_cmd.sh", ["#!/usr/bin/env bash\n", "mkfifo -m 644 tmp_fifo\n", "echo 0 > tmp_fifo"])

    # execute multisession queries
    api_query = APIQuery(compose_api_queries_pipe_names(
            global_settings.api_dir, query))
    assert api_query.wait_until_valid(0.1, 30, True), f"Pipes for test {name} must have been created"
    stall_pipe_readers=[]
    background_process_readers_count = 1
    for i in range(0, background_process_readers_count):
        api_query.execute(f"SESSION_ID={i}")

    print("wait until output pipes created", file=sys.stdout, flush=True)
    for i in range(0, background_process_readers_count):
        api_query.__wait_result_pipe_creation__(str(i), 0.1, 30, True)

    print(f"Send signal to pids of {name}_server.sh", file=sys.stdout, flush=True)
    pids = list(ut_utils.get_pids(f"{name}_server.sh"))
    assert len(pids)
    for p in pids:
        print(f"Kill {name}_server.sh given pid: {p}")
        os.killpg(os.getpgid(p), signal.SIGKILL)

    print(f"Wait for termination {name}_server.sh", file=sys.stdout, flush=True)
    for p in pids:
        try:
            os.waitpid(p, 0)
            print(f"{name}_server.sh finished given pid: {p}")
        except Exception:
            pass

    print(f"Check pids of {name}_server.sh", file=sys.stdout, flush=True)
    pidds = list()
    try:
        pidds = list(ut_utils.get_pids(f"{name}_server.sh"))
    except Exception:
        pass

    assert len(pidds) == 0
