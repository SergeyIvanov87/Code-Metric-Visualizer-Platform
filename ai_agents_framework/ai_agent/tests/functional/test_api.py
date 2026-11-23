#!/usr/bin/python

import os
import pytest
import shutil

from time_utils import get_timestamp
from settings import Settings
from heartbeat import Heartbeat
from queries import FS_API_Executor
from utils import get_api_queries
from utils import get_files
from api_schema_utils import compose_api_queries_pipe_names
from api_fs_query import APIQueryInterruptibleInterruptible

global_settings = Settings()
executor = FS_API_Executor("/API", global_settings.api_dir, global_settings.domain_name_api_entry)
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())

def check_rag_add_api(query, pipes):
    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    api_query = APIQueryInterruptible(pipes)
    api_query.execute()
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    result = api_query.wait_result("", 0.1, 30, True)
    assert len(result)


def check_rag_add_data(query, pipes):
    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    api_query = APIQueryInterruptible(pipes)
    api_query.execute()
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    result = api_query.wait_result("", 0.1, 30, True)
    assert len(result)



def check_rag_bulk_add_api(query, pipes):
    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    api_query = APIQueryInterruptible(pipes)
    api_query.execute()
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    result = api_query.wait_result("", 0.1, 30, True)
    assert len(result)



def check_rag_delete_api(query, pipes):
    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    api_query = APIQueryInterruptible(pipes)
    api_query.execute()
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    result = api_query.wait_result("", 0.1, 30, True)
    assert len(result)



def check_rag_get_docs_api(query, pipes):
    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    api_query = APIQueryInterruptible(pipes)
    api_query.execute()
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    result = api_query.wait_result("", 0.1, 30, True)
    assert len(result)



def check_rag_sync_api(query, pipes):
    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    api_query = APIQueryInterruptible(pipes)
    api_query.execute()
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    result = api_query.wait_result("", 0.1, 30, True)
    assert len(result)



@pytest.fixture()
def project_cpp_files():
    global global_settings
    return set(get_files(global_settings.project_dir, r".*\.cpp"))

@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_nodes(name, query, project_cpp_files):
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
