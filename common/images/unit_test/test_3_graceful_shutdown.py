#!/usr/bin/python

import os
import pathlib
import pytest
import signal
import socket
import stat
import subprocess
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
    print(f"[TEST][CALLBACK]onQueryPostExecute BEGIN: {in_exec_param}", file=sys.stdout, flush=True)
    set_query_counter(1)
    print(f"[TEST][CALLBACK]onQueryPostExecute FINISH: {in_exec_param}", file=sys.stdout, flush=True)


@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_graceful_shutdown_pipes_client(name, query, run_around_tests):
    global global_settings
    print(f"Test start: {name}", file=sys.stdout, flush=True)

    current_query_counter_value = get_query_counter()

    # compose expected pipe names, based on query data
    communication_pipes = compose_api_queries_pipe_names(global_settings.api_dir, query)
    print(f"[TEST] Check base API pipes creation: {communication_pipes}", file=sys.stdout, flush=True)
    for p in communication_pipes:
        api_result_pipe_timeout_cycles = 0
        while not (os.path.exists(p) and stat.S_ISFIFO(os.stat(p).st_mode)):
            time.sleep(0.1)
            api_result_pipe_timeout_cycles += 1
            assert api_result_pipe_timeout_cycles <= 30

    # stub API executable to and send requesto to it simulate stucking on a dead-end pipes
    generated_api_rel_path = "generated"
    filesystem_utils.create_executable_file([global_settings.work_dir, generated_api_rel_path], "req_cmd.sh", ["#!/usr/bin/env bash\n", "echo 'starting'\n", "sleep infinity &\n", "wait $!\n", "echo 'finished'\n"])
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
        print(f"[TEST] waiting for query execution[{query_waiting_timeout_cycles}]", file=sys.stdout, flush=True)
        query_waiting_timeout_cycles += 1
        assert query_waiting_timeout_cycles <= 30
    current_query_counter_value = new_query_counter_value

    # Remove dead-nodes and unblock waiting threads
    deleted_files = remove_api_fs_pipes_node(global_settings.api_dir, "server", query["Query"], query["Method"])
    assert len(deleted_files)
    print(f"[TEST] server pipes have been releases {deleted_files}", file=sys.stdout, flush=True)
    deleted_files = remove_api_fs_pipes_node(global_settings.api_dir, "client", query["Query"], query["Method"])
    assert len(deleted_files)
    print(f"[TEST] client pipes have been releases {deleted_files}", file=sys.stdout, flush=True)
    print("[TEST] waiting threads must be unblocked", file=sys.stdout, flush=True)
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
    print(f"[TEST][CALLBACK]onQueryPreExecute BEGIN: {in_exec_param}", file=sys.stdout, flush=True)
    set_query_counter(1)
    print(f"[TEST][CALLBACK]onQueryPreExecute FINISH: {in_exec_param}", file=sys.stdout, flush=True)
    return in_exec_param + " blahblah=blahblah"


@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_graceful_shutdown_pipes_client_server(name, query, run_around_tests):
    global global_settings
    print(f"Test start: {name}", file=sys.stdout, flush=True)

    current_query_counter_value = get_query_counter()

    # compose expected pipe names, based on query data
    communication_pipes = compose_api_queries_pipe_names(global_settings.api_dir, query)
    print(f"[TEST] Check base API pipes creation: {communication_pipes}", file=sys.stdout, flush=True)
    for p in communication_pipes:
        api_result_pipe_timeout_cycles = 0
        while not (os.path.exists(p) and stat.S_ISFIFO(os.stat(p).st_mode)):
            time.sleep(0.1)
            api_result_pipe_timeout_cycles += 1
            assert api_result_pipe_timeout_cycles <= 30

    # stub API executable to and send requesto to it simulate stucking on a dead-end pipes
    # this query must stuck on a 'result' pipe, as it's execution will be blocked by infinity sleeping in a scipt below
    generated_api_rel_path = "generated"
    filesystem_utils.create_executable_file([global_settings.work_dir, generated_api_rel_path], "req_cmd.sh", ["#!/usr/bin/env bash\n", "sleep infinity &\n", "wait $!\n", "echo 'finishing'\n"])
    executors = []
    session_id = 0
    server_blocking_executor = ut_utils.APIExecutor(global_settings.api_dir, query, session_id, None, None, onQueryPostExecute)
    server_blocking_executor.run(1)
    executors.append(server_blocking_executor)

    # wait for query executed to prove the fact that thread have started and wait for an answer
    new_query_counter_value = current_query_counter_value
    query_waiting_timeout_cycles = 0
    while new_query_counter_value == current_query_counter_value:
        time.sleep(0.1)
        new_query_counter_value = get_query_counter()
        print(f"[TEST] waiting for server bloking query execution[{query_waiting_timeout_cycles}]", file=sys.stdout, flush=True)
        assert query_waiting_timeout_cycles <= 30
        query_waiting_timeout_cycles += 1
    current_query_counter_value = new_query_counter_value

    parallel_by_session = query.get("ParallelBySession", False)
    second_request_started = threading.Event()
    second_result_ready = threading.Event()

    def before_second_request(executor, arguments, additional_params):
        second_request_started.set()
        return onQueryPreExecute(executor, arguments, additional_params)

    def after_second_request(executor, arguments, additional_params):
        # APIExecutor calls this only after the session result FIFO exists.
        second_result_ready.set()

    session_id += 1
    second_executor = ut_utils.APIExecutor(
        global_settings.api_dir, query, session_id,
        None, before_second_request, after_second_request,
    )
    second_executor.run(1)
    executors.append(second_executor)

    assert second_request_started.wait(3), "Second client did not start"
    if parallel_by_session:
        # Different sessions must both be accepted while the first executor
        # remains blocked. Cleanup will deliver cancellation to both readers.
        assert second_result_ready.wait(3), "Parallel session was not accepted"
    else:
        # Legacy endpoints cannot accept the second request while busy. The
        # result FIFO must remain absent until the server is killed below.
        assert not second_result_ready.wait(0.2), "Serial endpoint accepted a second request"

    print(f"[TEST] Kill server {name}_server.sh", file=sys.stdout, flush=True)
    pids = list(ut_utils.get_pids(f"{name}_server.sh"))
    assert len(pids)
    for p in pids:
        print(f"[TEST] Kill {name}_server.sh given pid: {p}")
        os.killpg(os.getpgid(p), signal.SIGKILL)

    print(f"[TEST] Wait for termination {name}_server.sh", file=sys.stdout, flush=True)
    for p in pids:
        try:
            os.waitpid(p, 0)
            print(f"[TEST] {name}_server.sh finished given pid: {p}")
        except Exception:
            pass

    #time.sleep(30)
    unblocking_script_path=filesystem_utils.create_executable_file([global_settings.work_dir, generated_api_rel_path],
                                             "remove_api_fs_pipes_node.py",
                                             ["#!/usr/bin/env python\n",
                                              "import os\n",
                                              "from renew_pseudo_fs_pipes import remove_api_fs_pipes_node\n",
                                               f"deleted_files = remove_api_fs_pipes_node('{global_settings.api_dir}', 'server', '{query['Query']}', '{query['Method']}')\n",
                                               "if len(deleted_files) == 0:\n",
                                               "    os.exit(-1)\n",
                                               f"deleted_files = remove_api_fs_pipes_node('{global_settings.api_dir}', 'client', '{query['Query']}', '{query['Method']}')\n",
                                               "if len(deleted_files) == 0:\n",
                                               "    os.exit(-1)\n"
                                              ])
    print(f"[TEST] Remove dead-nodes and unblock waiting threads by executing a process: {unblocking_script_path}", file=sys.stdout, flush=True)
    unblocking_result = subprocess.run(
                [   sys.executable,
                    unblocking_script_path,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

    print(f"[TEST] Error: {unblocking_result.stderr}", file=sys.stdout, flush=True)
    assert unblocking_result.returncode == 0
    # DO NOT CALL remove_api_fs_pipes_node() directly!!!
    # It calls fork() to create a child process, which inherits a current thread from caller, which may cause blocking!!!
    #deleted_files = remove_api_fs_pipes_node(global_settings.api_dir, "server", query["Query"], query["Method"])
    #assert len(deleted_files)
    #print(f"[TEST] server pipes have been releases {deleted_files}", file=sys.stdout, flush=True)
    #deleted_files = remove_api_fs_pipes_node(global_settings.api_dir, "client", query["Query"], query["Method"])
    #assert len(deleted_files)
    #print(f"[TEST] client pipes have been releases {deleted_files}", file=sys.stdout, flush=True)

    print("[TEST] waiting threads must be unblocked", file=sys.stdout, flush=True)
    for executor in executors:
        executor.async_executor.join(timeout=20)
        assert not executor.async_executor.is_alive(), "Client remained blocked after cleanup"
    assert not len(executors[0].error_message)
    print(f"[TEST] Thread 0 has been unblocked and must be gracefully returned from a result pipe waiting", file=sys.stdout, flush=True)
    if parallel_by_session:
        assert not executors[1].error_message
        assert second_result_ready.is_set()
    else:
        assert executors[1].error_message
        assert not second_result_ready.is_set()
    print("[TEST] Both clients unblocked according to the endpoint execution mode", file=sys.stdout, flush=True)

    # pipes do not exist anymore
    for p in communication_pipes:
        assert not os.path.exists(p)

    # Include session-specific result FIFOs, not just the two base pipes.
    assert not list(pathlib.Path(communication_pipes[0]).parent.glob("result*"))
