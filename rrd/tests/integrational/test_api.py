#!/usr/bin/python

import os
import pytest
import shutil
import socket

import rrd_utils

from settings import Settings
from time_utils import get_timestamp
from heartbeat import Heartbeat
from queries import FS_API_Executor
from utils import get_api_queries
from utils import get_files
from utils import compose_api_queries_pipe_names
from utils import wait_until_pipe_exist

from api_fs_query import APIQuery


global_settings = Settings()
executor = FS_API_Executor("/API", global_settings.api_dir, global_settings.domain_name_api_entry)
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())

def check_analytic_api(query, pipes, exec_params, session_id_value):
    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    api_query = APIQuery(pipes)
    api_query.execute(exec_params)
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    xml = api_query.wait_result(session_id_value, 0.1, 30, True)
    assert len(xml)


def check_rrd_api(query, pipes, exec_params, session_id_value):
    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    api_query = APIQuery(pipes)
    api_query.execute(exec_params)
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    xml = api_query.wait_result(session_id_value, 0.1, 30, True)
    assert len(xml)

def make_rrd_names_from(source_files, rrd_volume_mount_path):
    rrd_dirs = []
    rrd_files = []
    for f in source_files:
        f_splitted = os.path.normpath(f).split(os.path.sep)
        f_splitted[-1] = rrd_utils.canonize_rrd_source_name(f_splitted[-1])
        rrd_dirs.append(os.path.join(rrd_volume_mount_path, *f_splitted))
        f_splitted[-1] = f_splitted[-1] + ".rrd"
        rrd_files.append(os.path.join(rrd_volume_mount_path, *f_splitted))
    return rrd_dirs, rrd_files

def check_rrd_collect_api(query, pipes, exec_params, session_id_value):
    h = Heartbeat()
    h.run(f"Test 'check_rrd_collect_api' is in progress...")
    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    api_query = APIQuery(pipes)
    api_query.execute(exec_params)
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    out = api_query.wait_result(session_id_value, 0.1, 30, True)
    h.stop()
    assert len(out) == 0


def check_rrd_select_api(query, pipes, exec_params, session_id_value):
    # prepare RRD files
    global executor
    h = Heartbeat()
    h.run(f"Test 'check_rrd_select_api' is in progress...")
    executor.execute("rrd_collect", exec_params, session_id_value)
    h.stop()

    # seach appropriated RRD files using `rrd_select` api
    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    api_query = APIQuery(pipes)
    api_query.execute(exec_params)
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    out = api_query.wait_result(session_id_value, 0.1, 30, True)

    assert len(out)
    assert out.find(".rrd") != -1

def check_rrd_view_api(query, pipes, exec_params, session_id_value):
    # prepare RRD files
    global executor
    h = Heartbeat()
    h.run(f"Test 'check_rrd_view_api' is in progress...")
    executor.execute("rrd_collect", exec_params, session_id_value)
    h.stop()

    api_query = APIQuery(pipes)
    api_query.execute(exec_params)
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    out = api_query.wait_result(session_id_value, 0.1, 30, True)

    assert len(out)
    assert out.find("TIME") != -1
    assert out.find("mmcc") != -1
    assert out.find("tmcc") != -1
    assert out.find("sif") != -1
    assert out.find("lif") != -1



def check_rrd_plot_view_api(query, pipes, exec_params, session_id_value):
    # prepare RRD files
    global executor
    h = Heartbeat()
    h.run(f"Test 'check_rrd_plot_view_api' is in progress...")
    executor.execute("rrd_collect", exec_params, session_id_value)
    h.stop()

    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    api_query = APIQuery(pipes)
    api_query.execute(exec_params)
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    out = api_query.wait_binary_result(session_id_value, 0.1, 30, True)

    assert len(out)

@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_nodes(name, query):
    # compose expected pipe names, based on query data
    session_id_value = socket.gethostname() + "_" + name
    print(f"{get_timestamp()}\tExecute test: {name}, session: {session_id_value}")
    global global_settings

    pipes = compose_api_queries_pipe_names(global_settings.api_dir, query, session_id_value)
    exec_params = "SESSION_ID=" + session_id_value

    if name == "analytic":
        check_analytic_api(query, pipes, exec_params, session_id_value)
    elif name == "rrd":
        check_rrd_api(query, pipes, exec_params, session_id_value)
    elif name == "rrd_collect":
        check_rrd_collect_api(query, pipes, exec_params, session_id_value)
    elif name == "rrd_select":
        check_rrd_select_api(query, pipes, exec_params, session_id_value)
    elif name == "rrd_view":
        check_rrd_view_api(query, pipes, exec_params, session_id_value)
    elif name == "rrd_plot_view":
        check_rrd_plot_view_api(query, pipes, exec_params, session_id_value)
    else:
        assert 0
