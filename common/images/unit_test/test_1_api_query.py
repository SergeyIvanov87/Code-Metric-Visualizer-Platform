#!/usr/bin/python

import os
import pathlib
import pytest
import stat
import sys
import time
import threading

from multiprocessing import Process, Queue
from settings import Settings
from utils import get_api_queries
from api_schema_utils import compose_api_queries_pipe_names
from api_fs_query import APIQuery
from api_fs_query import APIQueryInterruptible

global_settings = Settings()
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())


def test_api_query_fail_init_not_enough_pipes():
    catched = False
    try:
        query = APIQuery("")
    except RuntimeError as e:
        catched = True

    assert catched, "APIQuery must be created at lest from 2 pipes"

def test_api_query_fail_bad_names():
    catched = False
    try:
        query = APIQuery(["aaaa", "bbbb"])
    except RuntimeError as e:
        catched = True

    assert catched, "APIQuery must be created at lest from 2 pipes"


def test_api_query_not_valid():
    query = APIQuery(["exec", "result"])
    assert not query.is_valid(), "APIQuery valid only if pipes exist"

def test_api_query_valid():
    pipes = ["exec", "result"]
    for p in pipes:
        if os.path.exists(p):
            os.unlink(p)
        os.mkfifo(p)

    query = APIQuery(pipes)
    assert query.is_valid(), "APIQuery valid if both pipes exist"


def test_api_query_valid_suppressed_main_result_pipe_name_resolution():
    pipes = ["exec", "result_session_id", "result"]
    assert APIQuery.__get_main_result_pipe__(pipes) == "result"

    pipes_ext = ["exec", "result_session_id.txt", "result.txt"]
    assert APIQuery.__get_main_result_pipe__(pipes_ext) == "result.txt"

def test_api_query_valid_suppressed_main_result_name():
    pipes = ["exec", "result"]
    for p in pipes:
        if os.path.exists(p):
            os.unlink(p)
        os.mkfifo(p)

    pipes_for_queries = ["exec", "result_session_id"]
    query = APIQuery(pipes_for_queries)
    assert query.is_valid(), "APIQuery must be valid if main result piep exist"

@pytest.mark.parametrize("name,query", testdata)
def test_api_query_execute_wait_result(name, query, run_around_tests):
    global global_settings
    print(f"Test start: {name}", file=sys.stdout, flush=True)

    query = APIQuery(compose_api_queries_pipe_names(global_settings.api_dir, query))
    assert query.wait_until_valid(0.1, 30, True), f"Pipes for test {name} must have been created"

    # check API transaction
    print(f"Check API transaction: {name}", file=sys.stdout, flush=True)
    query.execute()
    result = query.wait_result("", 0.1, 30, True)
    print(f"Transaction result: {result}", file=sys.stdout, flush=True)
    assert len(result)

    print(f"Check API session transaction: {name}", file=sys.stdout, flush=True)
    session_id_1 = "1"
    session_id_2 = "2"
    query.execute("SESSION_ID=" + session_id_1 + "\n" + "SESSION_ID=" + session_id_2)
    result_1 = query.wait_result(session_id_1, 0.1, 30, True)
    print(f"Transaction session \"{session_id_1}\" result: {result_1}", file=sys.stdout, flush=True)
    assert len(result_1)
    result_2 = query.wait_result(session_id_2, 0.1, 30, True)
    print(f"Transaction session \"{session_id_2}\" result: {result_2}", file=sys.stdout, flush=True)
    assert len(result_2)

def test_api_interruptible_valid_suppressed_main_result_pipe_name_resolution():
    pipes = ["exec", "result_session_id", "result"]
    assert APIQueryInterruptible.__get_main_result_pipe__(pipes) == "result"

    pipes_ext = ["exec", "result_session_id.txt", "result.txt"]
    assert APIQueryInterruptible.__get_main_result_pipe__(pipes_ext) == "result.txt"

    pipes = ["exec", "result_session_id", "result"]
    assert APIQueryInterruptible.__get_result_pipe__(pipes) == "result"

    pipes_ext = ["exec", "result_session_id.txt", "result.txt"]
    assert APIQueryInterruptible.__get_result_pipe__(pipes_ext) == "result.txt"

    pipes = ["exec", "result_session_id", "result"]
    assert APIQueryInterruptible.__get_result_pipe__(pipes, "session_id") == "result_session_id"

    pipes_ext = ["exec", "result.txt_session_id", "result.txt"]
    assert APIQueryInterruptible.__get_result_pipe__(pipes_ext, "session_id") == "result.txt_session_id"


@pytest.mark.parametrize("name,query", testdata)
def test_api_interruptible_execute_wait_result(name, query, run_around_tests):
    global global_settings
    print(f"Test start: {name}", file=sys.stdout, flush=True)

    query = APIQueryInterruptible(compose_api_queries_pipe_names(global_settings.api_dir, query), remove_session_pipe_on_result_done = False)
    assert query.wait_until_valid(0.1, 30, True), f"Pipes for test {name} must have been created"

    # check API transaction
    print(f"Check API transaction: {name}", file=sys.stdout, flush=True)
    status, timeout = query.execute(3)
    assert status, f"exec() must not be interrupted"
    status, result, timeout = query.wait_result(3, "", 0.1, 30, True)
    print(f"Transaction result: {result}", file=sys.stdout, flush=True)
    assert status, f"wait_result() must not be interrupted"
    assert len(result)

    print(f"Check API session transaction: {name}", file=sys.stdout, flush=True)
    session_id_1 = "1"
    session_id_2 = "2"
    status, timeout = query.execute(3, "SESSION_ID=" + session_id_1 + "\n" + "SESSION_ID=" + session_id_2)
    assert status, f"execute() must not be interrupted"
    status, result_1, timeout = query.wait_result(3, session_id_1, 0.1, 30, True)
    print(f"Transaction session \"{session_id_1}\" result: {result_1}", file=sys.stdout, flush=True)
    assert status, f"wait_result() for session {session_id_1} must not be interrupted"
    assert len(result_1)
    status, result_2, timeout = query.wait_result(3, session_id_2, 0.1, 30, True)
    print(f"Transaction session \"{session_id_2}\" result: {result_2}", file=sys.stdout, flush=True)
    assert status, f"wait_result() for session {session_id_2} must not be interrupted"
    assert len(result_2)


@pytest.mark.parametrize("name,query", testdata)
def test_api_interruptible_execute_ka_probe_wait_result(name, query, run_around_tests):
    global global_settings
    print(f"Test start: {name}", file=sys.stdout, flush=True)

    query = APIQueryInterruptible(compose_api_queries_pipe_names(global_settings.api_dir, query), remove_session_pipe_on_result_done = False)
    assert query.wait_until_valid(0.1, 30, True), f"Pipes for test {name} must have been created"

    # check API KA transaction
    ka_tag = str(time.time() * 1000)
    print(f"Check API KA transaction: {name}, ka_tag: {ka_tag}", file=sys.stdout, flush=True)
    status, timeout = query.execute(3, "API_KEEP_ALIVE_CHECK=" + ka_tag)
    assert status, f"exec() must not be interrupted"
    status, result, timeout = query.wait_result(3, "", 0.1, 30, True)
    assert status, f"wait_result() must not be interrupted"
    assert result == ka_tag, f"result: {result}, must match ka tag: {ka_tag}"

    print(f"Check API KA session transaction: {name}, ka_tag: {ka_tag}", file=sys.stdout, flush=True)
    session_id_1 = "1"
    session_id_2 = "2"
    status, timeout = query.execute(3, "API_KEEP_ALIVE_CHECK=" + ka_tag + " SESSION_ID=" + session_id_1 + "\n" + "API_KEEP_ALIVE_CHECK=" + ka_tag + " SESSION_ID=" + session_id_2)
    assert status, f"execute() must not be interrupted"
    status, result_1, timeout = query.wait_result(3, session_id_1, 0.1, 30, True)
    assert status, f"wait_result() for session {session_id_1} must not be interrupted"
    assert result_1 == ka_tag, f"result_1: {result_1}, must match ka tag: {ka_tag}"
    status, result_2, timeout = query.wait_result(3, session_id_2, 0.1, 30, True)
    assert status, f"wait_result() for session {session_id_2} must not be interrupted"
    assert result_2 == ka_tag, f"result_2: {result_2}, must match ka tag: {ka_tag}"

def test_api_interruptible_interruption_check():
    pipes = ["exec", "result"]
    for p in pipes:
        if os.path.exists(p):
            os.unlink(p)
        os.mkfifo(p)

    print(f"Test start: test_api_interruptible_interruption_check", file=sys.stdout, flush=True)
    query = APIQueryInterruptible(pipes, remove_session_pipe_on_result_done = True)

    # check API transaction
    print(f"Check API transaction", file=sys.stdout, flush=True)
    status, timeout = query.execute(10)
    assert not status, f"execute() must be interrupted"
    assert timeout < 0.5, f"execute() must run out of time, timeout: {timeout}"

    status, result, timeout = query.wait_result(10, "", 0.1, 100, True)
    assert not status, f"wait_result() must be interrupted"
    assert timeout < 0.5, f"wait_result() must run out of time, timeout: {timeout}"


def test_api_interruptible_large_write_times_out_when_reader_stalls():
    pipe = "exec"
    if os.path.exists(pipe):
        os.unlink(pipe)
    os.mkfifo(pipe)

    # Keep a reader connected, but deliberately do not drain the FIFO. This
    # reproduces a service which accepts a query and then stops consuming it.
    reader = os.open(pipe, os.O_RDONLY | os.O_NONBLOCK)
    try:
        query = APIQueryInterruptible([pipe, "result"])
        started = time.monotonic()
        status, timeout = query.execute(0.2, "VALUE=" + ("x" * 1_000_000))
        elapsed = time.monotonic() - started
    finally:
        os.close(reader)

    assert not status, "a partially written query must not be reported as accepted"
    assert timeout == 0
    assert elapsed < 1.5, f"stalled FIFO write did not respect its timeout: {elapsed}"


def test_api_interruptible_large_write_retries_while_reader_is_slow():
    pipe = "slow_exec"
    if os.path.exists(pipe):
        os.unlink(pipe)
    os.mkfifo(pipe)

    payload = "VALUE=" + ("x" * 128_000)
    expected = (payload + os.linesep).encode()
    received = bytearray()
    stop_reader = threading.Event()
    reader = os.open(pipe, os.O_RDONLY | os.O_NONBLOCK)

    def drain_slowly():
        while len(received) < len(expected) and not stop_reader.is_set():
            chunk = os.read(reader, 1024)
            if chunk:
                received.extend(chunk)
            time.sleep(0.01)

    reader_thread = threading.Thread(target=drain_slowly)
    reader_thread.start()
    try:
        query = APIQueryInterruptible([pipe, "result"])
        status, timeout = query.execute(5, payload)
        reader_thread.join(timeout=2)
    finally:
        stop_reader.set()
        reader_thread.join(timeout=1)
        os.close(reader)

    assert status, "a slow reader must be allowed to drain and accept the full query"
    assert timeout > 0
    assert bytes(received) == expected


def parallel_exec(index, query, message_to_send, polling_second_count = 1):
        status, timeout = query.execute(30, message_to_send)
        print(f"Process: {index} has finished, status: {status}, timeout: {timeout}")

def test_api_interruptible_multiple_queries():
    pipes = ["exec", "result"]
    for p in pipes:
        if os.path.exists(p):
            os.unlink(p)
        os.mkfifo(p)

    print(f"Test start: test_api_interruptible_interruption_check", file=sys.stdout, flush=True)
    query = APIQueryInterruptible(pipes, remove_session_pipe_on_result_done = True)

    # check API transaction
    transactions_count = 10
    print(f"Check API transactions: {transactions_count}", file=sys.stdout, flush=True)
    async_jobs = []
    for n in range(0,transactions_count):
        print(f"Launch process: [{n}/{transactions_count}]", file=sys.stdout, flush=True)
        async_executor = Process(target=parallel_exec, args=[n, query, "VALUE=" + str(n)])
        async_executor.start()
        async_jobs.append(async_executor)

    read_queries=0
    while read_queries < transactions_count:
        with open(pipes[0], "r") as pout:
            print(f"Multiple waiting reading is starting: [{read_queries}/{transactions_count}]", file=sys.stdout, flush=True)
            result = pout.read()
            print(f"Multiple waiting has finished result: {result}", file=sys.stdout, flush=True)
        lines = result.split();
        for l in lines:
            assert len(l.split('=')) == 2
            read_queries += 1

    for j in async_jobs:
        j.join()
