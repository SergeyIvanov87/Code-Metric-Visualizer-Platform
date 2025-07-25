#!/usr/bin/python

import os
import pytest
import shutil

import rrd_utils

from time_utils import get_timestamp
from settings import Settings
from heartbeat import Heartbeat
from queries import FS_API_Executor
from utils import get_api_queries
from utils import get_files
from api_schema_utils import compose_api_queries_pipe_names
from api_fs_query import APIQuery

global_settings = Settings()
executor = FS_API_Executor("/API", global_settings.api_dir, global_settings.domain_name_api_entry)
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())

def check_analytic_api(query, pipes, expected_files):
    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    api_query = APIQuery(pipes)
    api_query.execute()
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    xml = api_query.wait_result("", 0.1, 30, True)
    assert len(xml)


def check_rrd_api(query, pipes, expected_files):
    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    api_query = APIQuery(pipes)
    api_query.execute()
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    xml = api_query.wait_result("", 0.1, 30, True)
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

def check_rrd_collect_api(query, pipes, project_cpp_files):
    rrd_storage = os.getenv('RRD_DATA_STORAGE_DIR', '')
    shutil.rmtree(os.path.join(rrd_storage, "mnt"), ignore_errors=True)

    rrd_dirs, rrd_files = make_rrd_names_from(project_cpp_files, rrd_storage)
    for f in rrd_files:
        assert not os.path.isfile(f)

    h = Heartbeat()
    h.run(f"{get_timestamp()}\tTest 'check_rrd_collect_api' is in progress...")
    api_query = APIQuery(pipes)
    api_query.execute()
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    out = api_query.wait_result("", 0.1, 30, True)
    h.stop()
    assert len(out) != 0


    for f in rrd_files:
        assert os.path.isfile(f)
        os.unlink(f)
    for d in rrd_dirs:
        assert os.path.isdir(d)
        shutil.rmtree(d)

def check_rrd_select_api(query, pipes, project_cpp_files):
    # prepare RRD files
    global executor
    h = Heartbeat()
    h.run(f"{get_timestamp()}\tTest 'check_rrd_select_api' is in progress...")
    out = executor.execute("rrd_collect", "TRACER_ID=check_rrd_select_api_rrd_collect_helper")
    h.stop()
    assert len(out) == 0, "check_rrd_select_api_rrd_collect_helper has been failed"

    # seach appropriated RRD files using `rrd_select` api
    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    api_query = APIQuery(pipes)
    api_query.execute()
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    out = api_query.wait_result("", 0.1, 30, True)
    rrd_storage = os.getenv('RRD_DATA_STORAGE_DIR', '')
    shutil.rmtree(os.path.join(rrd_storage, "mnt"), ignore_errors=True)

    assert len(out)
    assert out.find(".rrd") != -1

def check_rrd_view_api(query, pipes):
    # prepare RRD files
    global executor
    h = Heartbeat()
    h.run(f"{get_timestamp()}\tTest 'check_rrd_view_api' is in progress...")
    out = executor.execute("rrd_collect", "TRACER_ID=check_rrd_view_api_rrd_collect_helper")
    h.stop()
    assert len(out) == 0, "check_rrd_view_api_rrd_collect_helper has been failed"

    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    api_query = APIQuery(pipes)
    api_query.execute()
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    out = api_query.wait_result("", 0.1, 30, True)
    rrd_storage = os.getenv('RRD_DATA_STORAGE_DIR', '')
    shutil.rmtree(os.path.join(rrd_storage, "mnt"), ignore_errors=True)

    assert len(out)
    assert out.find("TIME") != -1
    assert out.find("mmcc") != -1
    assert out.find("tmcc") != -1
    assert out.find("sif") != -1
    assert out.find("lif") != -1



def check_rrd_plot_view_api(query, pipes):
    # prepare RRD files
    global executor
    h = Heartbeat()
    h.run(f"{get_timestamp()}\tTest 'check_rrd_plot_view_api' is in progress...")
    out = executor.execute("rrd_collect", "TRACER_ID=check_rrd_plot_view_api_rrd_collect_helper")
    h.stop()
    assert len(out) == 0, "check_rrd_view_api_rrd_collect_helper has been failed"

    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    api_query = APIQuery(pipes)
    api_query.execute()
    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    out = api_query.wait_binary_result("", 0.1, 30, True)
    rrd_storage = os.getenv('RRD_DATA_STORAGE_DIR', '')
    shutil.rmtree(os.path.join(rrd_storage, "mnt"), ignore_errors=True)

    assert len(out)

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

    if name == "analytic":
        check_analytic_api(query, pipes, project_cpp_files)
    elif name == "rrd":
        check_rrd_api(query, pipes, project_cpp_files)
    elif name == "rrd_collect":
        check_rrd_collect_api(query, pipes, project_cpp_files)
    elif name == "rrd_select":
        check_rrd_select_api(query, pipes, project_cpp_files)
    elif name == "rrd_view":
        check_rrd_view_api(query, pipes)
    elif name == "rrd_plot_view":
        check_rrd_plot_view_api(query, pipes)
    else:
        assert 0
