#!/usr/bin/python

import os
import pathlib
import pytest
import signal
import socket
import stat
import sys
import time
import threading
import ut_utils

import filesystem_utils
from settings import Settings
from utils import get_api_queries
from api_schema_utils import compose_api_queries_pipe_names
from async_executor import AsyncExecutor
from api_fs_query import APIQuery
from renew_pseudo_fs_pipes import remove_api_fs_pipes_node

global_settings = Settings()
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())

query_counter_lock = threading.Lock()
query_counter = 0

def get_query_counter():
    global query_counter_lock
    global query_counter

    value = 0
    query_counter_lock.acquire()
    value = query_counter
    query_counter_lock.release()
    return value

def set_query_counter(value):
    global query_counter_lock
    global query_counter

    old_value = 0
    query_counter_lock.acquire()
    old_value = query_counter
    query_counter += value
    query_counter_lock.release()
    return old_value


def onQueryPostExecute(api_exec_object, in_exec_param, additional_params):
    print(f"onQueryPostExecute: {in_exec_param}", file=sys.stdout, flush=True)
    set_query_counter(1)


@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_graceful_shutdown_pipes_client(name, query, run_around_tests):
    global global_settings
    print(f"Test start: {name}", file=sys.stdout, flush=True)

    current_query_counter_value = get_query_counter()

    # compose expected pipe names, based on query data
    communication_pipes = compose_api_queries_pipe_names(global_settings.api_dir, query)
    print(f"Check base API pipes creation: {communication_pipes}", file=sys.stdout, flush=True)
    for p in communication_pipes:
        api_result_pipe_timeout_cycles = 0
        while not (os.path.exists(p) and stat.S_ISFIFO(os.stat(p).st_mode)):
            time.sleep(0.1)
            api_result_pipe_timeout_cycles += 1
            assert api_result_pipe_timeout_cycles <= 30

    # stub API executable to and send requesto to it simulate stucking on a dead-end pipes
    generated_api_rel_path = "generated"
    filesystem_utils.create_executable_file([global_settings.work_dir, generated_api_rel_path], "req_cmd.sh", ["#!/usr/bin/env bash\n", "sleep infinity &\n", "wait $!"])
    executors = []
    session_id = 0
    executor = ut_utils.APIExecutor(global_settings.api_dir, query, session_id, None, None, onQueryPostExecute)
    executor.run(1)
    executors.append(executor)

    # wait for query executed to reflect that thread have started and wait for an answer
    new_query_counter_value = current_query_counter_value
    query_waiting_timeout_cycles = 0
    while new_query_counter_value == current_query_counter_value:
        time.sleep(0.1)
        new_query_counter_value = get_query_counter()
        print(f"waiting for query execution[{query_waiting_timeout_cycles}]", file=sys.stdout, flush=True)
        query_waiting_timeout_cycles += 1
        assert query_waiting_timeout_cycles <= 30
    current_query_counter_value = new_query_counter_value

    # Remove dead-nodes and unblock waiting threads
    deleted_files = remove_api_fs_pipes_node(global_settings.api_dir, "server", query["Query"], query["Method"])
    assert len(deleted_files)
    deleted_files = remove_api_fs_pipes_node(global_settings.api_dir, "client", query["Query"], query["Method"])
    assert len(deleted_files)

    print("waiting threads must be unblocked", file=sys.stdout, flush=True)
    for e in executors:
        e.join()

    # pipes do not exist anymore
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
    filesystem_utils.create_executable_file([global_settings.work_dir, generated_api_rel_path], "req_cmd.sh", ["#!/usr/bin/env bash\n", "mkfifo -m 644 tmp_fifo\n", "echo 0 > tmp_fifo"])

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


def onQueryPreExecute(api_exec_object, in_exec_param, additional_params):
    print(f"onQueryPreExecute: {in_exec_param}", file=sys.stdout, flush=True)
    set_query_counter(1)
    return in_exec_param + " blahblah=blahblah"


@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_graceful_shutdown_pipes_client_server(name, query, run_around_tests):
    global global_settings
    print(f"Test start: {name}", file=sys.stdout, flush=True)

    current_query_counter_value = get_query_counter()

    # compose expected pipe names, based on query data
    communication_pipes = compose_api_queries_pipe_names(global_settings.api_dir, query)
    print(f"Check base API pipes creation: {communication_pipes}", file=sys.stdout, flush=True)
    for p in communication_pipes:
        api_result_pipe_timeout_cycles = 0
        while not (os.path.exists(p) and stat.S_ISFIFO(os.stat(p).st_mode)):
            time.sleep(0.1)
            api_result_pipe_timeout_cycles += 1
            assert api_result_pipe_timeout_cycles <= 30

    # stub API executable to and send requesto to it simulate stucking on a dead-end pipes
    generated_api_rel_path = "generated"
    filesystem_utils.create_executable_file([global_settings.work_dir, generated_api_rel_path], "req_cmd.sh", ["#!/usr/bin/env bash\n", "sleep infinity &\n", "wait $!"])
    executors = []
    session_id = 0
    server_blocking_executor = ut_utils.APIExecutor(global_settings.api_dir, query, session_id, None, None, onQueryPostExecute)
    server_blocking_executor.run(1)
    executors.append(server_blocking_executor)

    # wait for query executed to reflect that thread have started and wait for an answer
    new_query_counter_value = current_query_counter_value
    query_waiting_timeout_cycles = 0
    while new_query_counter_value == current_query_counter_value:
        time.sleep(0.1)
        new_query_counter_value = get_query_counter()
        print(f"waiting for server bloking query execution[{query_waiting_timeout_cycles}]", file=sys.stdout, flush=True)
        assert query_waiting_timeout_cycles <= 30
        query_waiting_timeout_cycles += 1
    current_query_counter_value = new_query_counter_value

    print(f"Server must be blocked, release the blocked client")
    blocked_cliend_executor = ut_utils.APIExecutor(global_settings.api_dir, query, session_id, None, onQueryPreExecute, None)
    blocked_cliend_executor.run(1)
    executors.append(blocked_cliend_executor)

    # wait for query executed to reflect that blocked client have started and trygin to execute the query
    new_query_counter_value = current_query_counter_value
    query_waiting_timeout_cycles = 0
    while new_query_counter_value == current_query_counter_value:
        time.sleep(0.1)
        new_query_counter_value = get_query_counter()
        print(f"waiting for blocking in client before query execution[{query_waiting_timeout_cycles}]", file=sys.stdout, flush=True)
        assert query_waiting_timeout_cycles <= 30
        query_waiting_timeout_cycles += 1
    current_query_counter_value = new_query_counter_value

    print(f"Kill server {name}_server.sh", file=sys.stdout, flush=True)
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

    print(f"Remove dead-nodes and unblock waiting threads")
    deleted_files = remove_api_fs_pipes_node(global_settings.api_dir, "server", query["Query"], query["Method"])
    assert len(deleted_files)
    deleted_files = remove_api_fs_pipes_node(global_settings.api_dir, "client", query["Query"], query["Method"])
    assert len(deleted_files)

    print("waiting threads must be unblocked", file=sys.stdout, flush=True)
    executors[0].join()
    assert not len(executors[0].error_message)
    executors[1].join()
    assert len(executors[1].error_message)

    # pipes do not exist anymore
    for p in communication_pipes:
        assert not os.path.exists(p)
