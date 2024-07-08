#!/usr/bin/python

import os
import pathlib
import pytest
import socket
import stat
import sys
import time

from settings import Settings
from utils import get_api_queries
from utils import compose_api_queries_pipe_names
from async_executor import AsyncExecutor
from api_fs_query import APIQuery
from renew_pseudo_fs_pipes import remove_api_fs_pipes_node

global_settings = Settings()
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())


@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_graceful_shutdown_pipes(name, query, run_around_tests):
    global global_settings
    print(f"Test start: {name}", file=sys.stdout, flush=True)

    # compose expected pipe names, based on query data
    communication_pipes = compose_api_queries_pipe_names(global_settings.api_dir, query)
    # pipes exist
    print(f"Check base API pipes: {communication_pipes}", file=sys.stdout, flush=True)
    for p in communication_pipes:
        api_result_pipe_timeout_cycles = 0
        while not (os.path.exists(p) and stat.S_ISFIFO(os.stat(p).st_mode)):
            time.sleep(0.1)
            api_result_pipe_timeout_cycles += 1
            assert api_result_pipe_timeout_cycles <= 30


    req_type = query["Method"]
    req_api = query["Query"]
    deleted_files = remove_api_fs_pipes_node(global_settings.api_dir, query["Query"], query["Method"])
    assert len(deleted_files)

    # pipes do not exist
    for p in communication_pipes:
        assert not os.path.exists(p)
