#!/usr/bin/python

import os
import pathlib
import pytest
import stat
import sys
import time

from settings import Settings
from utils import get_api_queries
from api_schema_utils import compose_api_queries_pipe_names
from api_fs_query import APIQuery

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
