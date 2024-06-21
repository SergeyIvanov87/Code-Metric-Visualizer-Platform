#!/usr/bin/python

import os
import pytest
import shutil

import rrd_utils

from settings import Settings
from heartbeat import Heartbeat
from queries import FS_API_Executor
from utils import get_api_queries
from utils import get_files
from utils import compose_api_queries_pipe_names

global_settings = Settings()
executor = FS_API_Executor("/API", global_settings.api_dir, global_settings.domain_name_api_entry)
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())

def check_analytic_api(query, pipes, expected_files):
    xml = ""
    print(f"initiate test query: {query["Query"]}")
    with open(pipes[0], "w") as pin:
        pin.write("0")
    print(f"getting result of query: {query["Query"]}")
    with open(pipes[1], "r") as pout:
        xml = pout.read()
    assert len(xml)


def check_rrd_api(query, pipes, expected_files):
    xml = ""
    print(f"initiate test query: {query["Query"]}")
    with open(pipes[0], "w") as pin:
        pin.write("0")
    print(f"getting result of query: {query["Query"]}")
    with open(pipes[1], "r") as pout:
        xml = pout.read()
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
    h.run(f"Test 'check_rrd_collect_api' is in progress...")
    print(f"initiate test query: {query["Query"]}")
    with open(pipes[0], "w") as pin:
        pin.write("0")
    print(f"getting result of query: {query["Query"]}")
    with open(pipes[1], "r") as pout:
        out = pout.read()
        assert len(out) == 0
    h.stop()

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
    h.run(f"Test 'check_rrd_select_api' is in progress...")
    executor.execute("rrd_collect")
    h.stop()

    # seach appropriated RRD files using `rrd_select` api
    out = ""
    print(f"initiate test query: {query["Query"]}")
    with open(pipes[0], "w") as pin:
        pin.write("0")
    with open(pipes[1], "r") as pout:
        out = pout.read()
    print(f"getting result of query: {query["Query"]}")
    rrd_storage = os.getenv('RRD_DATA_STORAGE_DIR', '')
    shutil.rmtree(os.path.join(rrd_storage, "mnt"), ignore_errors=True)

    assert len(out)
    assert out.find(".rrd") != -1

def check_rrd_view_api(query, pipes):
    # prepare RRD files
    global executor
    h = Heartbeat()
    h.run(f"Test 'check_rrd_select_api' is in progress...")
    executor.execute("rrd_collect")
    h.stop()

    out = ""
    print(f"initiate test query: {query["Query"]}")
    with open(pipes[0], "w") as pin:
        pin.write("0")
    print(f"getting result of query: {query["Query"]}")
    with open(pipes[1], "r") as pout:
        out = pout.read()
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
    h.run(f"Test 'check_rrd_plot_view_api' is in progress...")
    executor.execute("rrd_collect")
    h.stop()

    out = ""
    print(f"initiate test query: {query["Query"]}")
    with open(pipes[0], "w") as pin:
        pin.write("0")
    print(f"getting result of query: {query["Query"]}")
    with open(pipes[1], "rb") as pout:
        out = pout.read()
    rrd_storage = os.getenv('RRD_DATA_STORAGE_DIR', '')
    shutil.rmtree(os.path.join(rrd_storage, "mnt"), ignore_errors=True)

    assert len(out)

@pytest.fixture()
def project_cpp_files():
    global global_settings
    return set(get_files(global_settings.project_dir, r".*\.cpp"))

@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_nodes(name, query, project_cpp_files):
    print(f"Execute test: {name}")
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
