#!/usr/bin/python

import json
import os
import pytest
import shutil

from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from time_utils import get_timestamp
from settings import Settings
from heartbeat import Heartbeat
from queries import FS_API_Executor
from utils import get_api_queries
from utils import get_files
from api_schema_utils import compose_api_queries_pipe_names
from api_fs_query import APIQueryInterruptible

global_settings = Settings()
RAG_DB_HOST = os.getenv('RAG_DB_HOST', '')
RAG_DB_PORT = os.getenv('RAG_DB_PORT', '')
executor = FS_API_Executor("/API", global_settings.api_dir, global_settings.domain_name_api_entry)
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())

def _load_cases(name):
    path = Path(__file__).parent / "api_test_cases" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _arguments(session_id, query):
    values = [f"SESSION_ID={session_id}"]
    values.extend(f"{name}={json.dumps(value)}" for name, value in query.items())
    return " ".join(values)


def _wait(api_query, timeout, session_id):
    status, result, _ = api_query.wait_result(
        timeout, session_id, 0.1, max(1, int(timeout / 0.1)), True
    )
    assert status, f"result timed out for session {session_id}"
    return json.loads(result)


def _assert_answer(result, expected, session_id):
    print(f"{get_timestamp()}\tSESSION_ID={session_id}, query result: {result}")
    assert result == expected, f"unexpected result for SESSION_ID={session_id}"


def _check_api(name, query, pipes):
    print(f"{get_timestamp()}\tinitiate test query: {query['Query']}")
    for session_id, test_case in _load_cases(name).items():
        timeout = int(test_case["query"].get("-timeout", 20))
        api_query = APIQueryInterruptible(pipes)
        status, timeout = api_query.execute(
            timeout, _arguments(session_id, test_case["query"])
        )
        assert status, f"query execution timed out for session {session_id}"
        result = _wait(api_query, timeout, session_id)
        _assert_answer(result, test_case["answer"], session_id)


def check_rag_add_api(query, pipes):
    _check_api("rag_add", query, pipes)


def check_rag_add_data(query, pipes):
    _check_api("rag_add_data", query, pipes)


def check_rag_bulk_add_api(query, pipes):
    for session_id, test_case in _load_cases("rag_bulk_add").items():
        api_query = APIQueryInterruptible(pipes)
        status, timeout = api_query.execute(
            20, _arguments(session_id, test_case["query"])
        )
        assert status, f"query execution timed out for session {session_id}"
        report = _wait(api_query, timeout, session_id)
        with Path(report["result"]).open(encoding="utf-8") as result_file:
            result = json.load(result_file)
        result.pop("timestamp", None)
        _assert_answer(result, test_case["answer"], session_id)


def check_rag_delete_api(query, pipes):
    _check_api("rag_delete", query, pipes)


def check_rag_get_docs_api(query, pipes):
    _check_api("rag_get_docs", query, pipes)


def check_rag_sync_api(query, pipes):
    _check_api("rag_sync", query, pipes)

@pytest.fixture()
def clear_rag_db():
    global global_settings
    global RAG_DB_HOST
    global RAG_DB_PORT
    collection = quote(global_settings.domain_name_api_entry, safe="")
    url = (
        f"http://{RAG_DB_HOST}:{RAG_DB_PORT}/api/v2/tenants/default_tenant/"
        f"databases/default_database/collections/{collection}"
    )
    try:
        with urlopen(Request(url, method="DELETE"), timeout=10):
            pass
    except HTTPError as error:
        if error.code != 404:
            raise


@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_nodes(name, query, clear_rag_db):
    print(f"{get_timestamp()}\tExecute test: {name}")
    global global_settings

    # compose expected pipe names, based on query data
    pipes = compose_api_queries_pipe_names(global_settings.api_dir, query)

    if name == "rag_add":
        check_rag_add_api(query, pipes)
    elif name == "rag_add_data":
        check_rag_add_data(query, pipes)
    elif name == "rag_bulk_add":
        check_rag_bulk_add_api(query, pipes)
    elif name == "rag_delete":
        check_rag_delete_api(query, pipes)
    elif name == "rag_get_docs":
        check_rag_get_docs_api(query, pipes)
    elif name == "rag_sync":
        check_rag_sync_api(query, pipes)
    else:
        assert 0, f"the query by name: {name} cannot be tested, no any test implemented. Please add a testcase for that quey"
