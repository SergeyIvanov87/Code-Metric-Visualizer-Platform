#!/usr/bin/python

import os
import pytest

from settings import Settings
from time_utils import get_timestamp
from utils import get_api_queries
from utils import get_files
from api_schema_utils import compose_api_queries_pipe_names
from api_fs_query import APIQuery

global_settings = Settings()
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())

def check_watch_list_api(query, pipes, expected_files):
    api_query = APIQuery(pipes)
    api_query.execute()
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    files_list = api_query.wait_result("", 0.1, 30, True).split()
    assert len(files_list)
    for f in files_list:
        assert f in expected_files

def check_statistic_api(query, pipes, expected_files):
    api_query = APIQuery(pipes)
    api_query.execute()
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    xml = api_query.wait_result("", 0.1, 30, True)
    assert len(xml)
    for f in expected_files:
        assert xml.find(os.path.basename(f)) != -1

def check_view_api(query, pipes, expected_files):
    api_query = APIQuery(pipes)
    api_query.execute()
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    view = api_query.wait_binary_result("", 0.1, 30, True)
    assert len(view)

def check_flamegraph_api(query, pipes):
    api_query = APIQuery(pipes)
    api_query.execute()
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    svg = api_query.wait_binary_result("", 0.1, 30, True)
    assert svg

@pytest.fixture()
def test_data_cpp_files():
    global global_settings
    return set(get_files(global_settings.project_dir, r".*\.cpp"))

@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_nodes(name, query, test_data_cpp_files):
    print(f"{get_timestamp()}\tExecute test: {name}")
    global global_settings

    # compose expected pipe names, based on query data
    pipes = compose_api_queries_pipe_names(global_settings.api_dir, query)

    if name == "watch_list":
        check_watch_list_api(query, pipes, test_data_cpp_files)
    elif name == "statistic":
        check_statistic_api(query, pipes, test_data_cpp_files)
    elif name == "view":
        check_view_api(query, pipes, test_data_cpp_files)
    elif name == "flamegraph":
        check_flamegraph_api(query, pipes)
    else:
        assert 0
