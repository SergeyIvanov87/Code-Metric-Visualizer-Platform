#!/usr/bin/python

import os
import pathlib
import pytest
import signal
import stat
import sys
import time
import threading
import ut_utils

import filesystem_utils
from settings import Settings
from utils import get_api_queries
from api_schema_utils import compose_api_queries_pipe_names
from api_fs_query import APIQuery
from renew_pseudo_fs_pipes import remove_api_fs_pipes_node

global_settings = Settings()
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())

from shutdown_test_utils import (
    assert_api_pipes_removed,
    cleanup_api_pipes,
    install_blocking_command,
    kill_process_groups,
    queries_for_execution_mode,
    wait_for_fifos,
)


@pytest.fixture(params=queries_for_execution_mode(testdata, False), ids=lambda item: item[0])
def traditional_query(request):
    return request.param


@pytest.fixture(params=queries_for_execution_mode(testdata, True), ids=lambda item: item[0])
def parallel_query(request):
    return request.param


@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_graceful_shutdown_pipes_client(name, query, run_around_tests):
    print(f"Test start: {name}", file=sys.stdout, flush=True)

    result_ready = threading.Event()

    def on_result_ready(executor, arguments, additional_params):
        result_ready.set()

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
    executor = ut_utils.APIExecutor(global_settings.api_dir, query, session_id, None, None, on_result_ready)
    executor.run(1)
    executors.append(executor)

    assert result_ready.wait(3), "Client did not reach its result FIFO"

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



# The traditional scenario retains its original contract: the first client
# waits for a result and the second must not obtain a session result FIFO.
def test_filesystem_api_graceful_shutdown_pipes_client_server(traditional_query, run_around_tests):
    name, query = traditional_query
    settings = Settings()
    communication_pipes = compose_api_queries_pipe_names(settings.api_dir, query)
    wait_for_fifos(communication_pipes)
    install_blocking_command(pathlib.Path(settings.work_dir) / "generated" / "req_cmd.sh")

    first_result_ready = threading.Event()
    second_request_started = threading.Event()
    second_result_ready = threading.Event()

    def on_first_result_ready(executor, arguments, additional_params):
        first_result_ready.set()

    def before_second_request(executor, arguments, additional_params):
        second_request_started.set()
        return arguments + " blahblah=blahblah"

    def on_second_result_ready(executor, arguments, additional_params):
        second_result_ready.set()

    first = ut_utils.APIExecutor(settings.api_dir, query, 0, None, None, on_first_result_ready)
    first.run(1)
    assert first_result_ready.wait(3), "First client did not reach its result FIFO"

    second = ut_utils.APIExecutor(
        settings.api_dir, query, 1, None, before_second_request, on_second_result_ready,
    )
    second.run(1)
    assert second_request_started.wait(3), "Second client did not start"
    assert not second_result_ready.wait(0.2), "Serial endpoint accepted a second request"

    pids = list(ut_utils.get_pids(f"{name}_server.sh"))
    assert pids
    kill_process_groups(pids)
    cleanup_api_pipes(settings.api_dir, query["Query"], query["Method"])

    for client in (first, second):
        client.async_executor.join(timeout=20)
        assert not client.async_executor.is_alive(), "Client remained blocked after cleanup"
    assert not first.error_message
    assert second.error_message
    assert not second_result_ready.is_set()
    assert_api_pipes_removed(communication_pipes)


def test_parallel_session_graceful_shutdown_pipes_client_server(parallel_query, run_around_tests):
    name, query = parallel_query
    settings = Settings()
    communication_pipes = compose_api_queries_pipe_names(settings.api_dir, query)
    wait_for_fifos(communication_pipes)
    install_blocking_command(pathlib.Path(settings.work_dir) / "generated" / "req_cmd.sh")

    first_result_ready = threading.Event()
    second_result_ready = threading.Event()
    results = {}

    def on_first_result_ready(executor, arguments, additional_params):
        first_result_ready.set()

    def on_second_result_ready(executor, arguments, additional_params):
        second_result_ready.set()

    def record_result(executor, arguments, additional_params, result):
        results[executor.index] = result.strip()

    first = ut_utils.APIExecutor(
        settings.api_dir, query, 0, None, None, on_first_result_ready, record_result,
    )
    first.run(1)
    assert first_result_ready.wait(3), "First client did not reach its result FIFO"

    second = ut_utils.APIExecutor(
        settings.api_dir, query, 1, None, None, on_second_result_ready, record_result,
    )
    second.run(1)
    assert second_result_ready.wait(3), "Second parallel session was not accepted"
    assert first.async_executor.is_alive()
    assert second.async_executor.is_alive()

    pids = list(ut_utils.get_pids(f"{name}_server.sh"))
    assert pids
    kill_process_groups(pids)
    cleanup_api_pipes(settings.api_dir, query["Query"], query["Method"])

    for client in (first, second):
        client.async_executor.join(timeout=20)
        assert not client.async_executor.is_alive(), "Client remained blocked after cleanup"
        assert not client.error_message
    assert results == {0: "[cancelled]", 1: "[cancelled]"}
    assert_api_pipes_removed(communication_pipes)
