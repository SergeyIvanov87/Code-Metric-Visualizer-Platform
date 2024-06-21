#!/usr/bin/python

import os
import pytest

from settings import Settings
from utils import get_api_queries
from utils import get_files
from utils import compose_api_queries_pipe_names

global_settings = Settings()
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())

def check_watch_list_api(query, pipes, expected_files):
    with open(pipes[0], "w") as pin:
        pin.write("0")
    with open(pipes[1], "r") as pout:
        files_list = pout.read().split()
        assert len(files_list)
        for f in files_list:
            assert f in expected_files
        return
    assert 0

def check_statistic_api(query, pipes, expected_files):
    with open(pipes[0], "w") as pin:
        pin.write("0")
    with open(pipes[1], "r") as pout:
        xml = pout.read()
        assert len(xml)
        for f in expected_files:
            assert xml.find(os.path.basename(f)) != -1
        return
    assert 0

def check_view_api(query, pipes, expected_files):
    with open(pipes[0], "w") as pin:
        pin.write("0")
    with open(pipes[1], "rb") as pout:
        view = pout.read()
        assert len(view)
        return
    assert 0

def check_flamegraph_api(query, pipes):
    with open(pipes[0], "w") as pin:
        pin.write("0")
    with open(pipes[1], "rb") as pout:
        svg = pout.read()
        assert svg
        return
    assert 0


@pytest.fixture()
def test_data_cpp_files():
    global global_settings
    return set(get_files(global_settings.project_dir, r".*\.cpp"))

@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_nodes(name, query, test_data_cpp_files):
    print(f"Execute test: {name}")
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
