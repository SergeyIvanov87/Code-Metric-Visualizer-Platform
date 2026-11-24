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

def check_rag_add_api(query, pipes):
    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    test_cases_path = Path(__file__).parent / "api_test_cases" / "rag_add.json"
    with test_cases_path.open(encoding="utf-8") as test_cases_file:
        test_cases = json.load(test_cases_file)

    for session_id, test_case in test_cases.items():
        timeout = int(test_case["query"].get("-timeout", 20))
        arguments = " ".join(
            [f"SESSION_ID={session_id}"]
            + [
                f"{name}={json.dumps(value)}"
                for name, value in test_case["query"].items()
            ]
        )
        api_query = APIQueryInterruptible(pipes)
        status, timeout = api_query.execute(timeout, arguments)
        assert status, f"query execution timed out for session {session_id}"

        print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
        status, result, _ = api_query.wait_result(
            timeout, session_id, 0.1, max(1, int(timeout / 0.1)), True
        )
        assert status, f"result timed out for session {session_id}"
        print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}, result:\n{result}")
        assert json.loads(result) == test_case["answer"]


def check_rag_add_data(query, pipes):
    pass

def check_rag_bulk_add_api(query, pipes):
    pass

def check_rag_delete_api(query, pipes):
    pass

def check_rag_get_docs_api(query, pipes):
    pass

def check_rag_sync_api(query, pipes):
    pass

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
