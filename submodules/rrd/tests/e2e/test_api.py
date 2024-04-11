#!/usr/bin/python

import os
import pytest

from settings import Settings
from utils import get_api_queries
from utils import get_files
from utils import compose_api_querie_pipe_names

global_settings = Settings()
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())


def check_analytic_api(query, pipes, expected_files):
    assert 1

def check_rrd_api(query, pipes, expected_files):
    assert 1

def check_rrd_collect_api(query, pipes, project_cpp_files):
    assert 1

def check_rrd_select_api(query, pipes):
    assert 1

def check_rrd_view_api(query, pipes):
    assert 1

def check_rrd_plot_view_api(query, pipes):
    assert 1

@pytest.fixture()
def project_cpp_files():
    global global_settings
    return set(get_files(global_settings.project_dir, r".*\.cpp"))

@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_nodes(name, query, project_cpp_files):
    global global_settings

    # compose expected pipe names, based on query data
    pipes = compose_api_querie_pipe_names(global_settings.api_dir, query)

    if name == "analytic":
        check_analytic_api(query, pipes, project_cpp_files)
    elif name == "rrd":
        check_rrd_api(query, pipes, project_cpp_files)
    elif name == "rrd_collect":
        check_rrd_collect_api(query, pipes, project_cpp_files)
    elif name == "rrd_select":
        check_rrd_select_api(query, pipes)
    elif name == "rrd_view":
        check_rrd_view_api(query, pipes)
    elif name == "rrd_plot_view":
        check_rrd_plot_view_api(query, pipes)
    else:
        assert 0
