#!/usr/bin/python

import os
import pytest
import socket

from settings import Settings
from queries import FS_API_Executor
from utils import get_api_queries
from utils import get_files
from utils import compose_api_queries_pipe_names
from utils import wait_until_pipe_exist

global_settings = Settings()
executor = FS_API_Executor("/API", global_settings.api_dir, global_settings.domain_name_api_entry)
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())

def check_watch_list_api(query, pipes, exec_params, session_id_value):
    print(f"initiate test query: {query["Query"]}")
    with open(pipes[0], "w") as pin:
        pin.write(exec_params)
    print(f"getting result of query: {query["Query"]}")
    wait_until_pipe_exist(pipes[1])
    with open(pipes[1], "r") as pout:
        files_list = pout.read().split()
        assert len(files_list)
        return
    assert 0

def check_statistic_api(query, pipes, exec_params, session_id_value):
    global executor
    watch_list_result = executor.execute("watch_list", exec_params, session_id_value)
    watch_files_list = watch_list_result.split()
    assert len(watch_files_list)

    print(f"initiate test query: {query["Query"]}")
    with open(pipes[0], "w") as pin:
        pin.write(exec_params)
    print(f"getting result of query: {query["Query"]}")
    wait_until_pipe_exist(pipes[1])
    with open(pipes[1], "r") as pout:
        xml = pout.read()
        assert len(xml)
        found_metrics=[]
        for f in watch_files_list:
            if xml.find(os.path.basename(f)) != -1:
                found_metrics.append(f)
        assert len(found_metrics) != 0
        return
    assert 0

def check_view_api(query, pipes, exec_params, session_id_value):
    print(f"initiate test query: {query["Query"]}")
    with open(pipes[0], "w") as pin:
        pin.write(exec_params)
    print(f"getting result of query: {query["Query"]}")
    wait_until_pipe_exist(pipes[1])
    with open(pipes[1], "rb") as pout:
        view = pout.read()
        assert len(view)
        return
    assert 0

def check_flamegraph_api(query, pipes, exec_params, session_id_value):
    print(f"initiate test query: {query["Query"]}")
    with open(pipes[0], "w") as pin:
        pin.write(exec_params)
    print(f"getting result of query: {query["Query"]}")
    wait_until_pipe_exist(pipes[1])
    with open(pipes[1], "rb") as pout:
        svg = pout.read()
        assert svg
        return
    assert 0


@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_nodes(name, query):
    print(f"Execute test: {name}")
    global global_settings

    # compose expected pipe names, based on query data
    session_id_value = socket.gethostname() + "_" + name
    pipes = compose_api_queries_pipe_names(global_settings.api_dir, query, session_id_value)
    exec_params = "SESSION_ID=" + session_id_value

    if name == "watch_list":
        check_watch_list_api(query, pipes, exec_params, session_id_value)
    elif name == "statistic":
        check_statistic_api(query, pipes, exec_params, session_id_value)
    elif name == "view":
        check_view_api(query, pipes, exec_params, session_id_value)
    elif name == "flamegraph":
        check_flamegraph_api(query, pipes, exec_params, session_id_value)
    else:
        assert 0
