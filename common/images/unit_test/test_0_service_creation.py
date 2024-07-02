#!/usr/bin/python

import os
import pathlib
import pytest
import stat
import sys
import time

from settings import Settings
from utils import get_api_queries
from utils import compose_api_queries_pipe_names

global_settings = Settings()
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())


@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_nodes_main_session(name, query, run_around_tests):
    global global_settings
    print(f"Test start: {name}", file=sys.stdout, flush=True)

    # compose expected pipe names, based on query data
    communication_pipes = compose_api_queries_pipe_names(global_settings.api_dir, query)

    # check that special files are really pipes
    print(f"Check API pipes: {communication_pipes}", file=sys.stdout, flush=True)
    for p in communication_pipes:
        api_result_pipe_timeout_cycles = 0
        while not (os.path.exists(p) and stat.S_ISFIFO(os.stat(p).st_mode)):
            time.sleep(0.1)
            api_result_pipe_timeout_cycles += 1
            assert api_result_pipe_timeout_cycles <= 30

    # check API transaction
    print(f"Check API transaction: {name}", file=sys.stdout, flush=True)
    with open(communication_pipes[0], "w") as pin:
        pin.write("0")
    with open(communication_pipes[1], "r") as pout:
        out = pout.read()
        print(f"Transaction result: {out}", file=sys.stdout, flush=True)
        assert len(out)
        return
    assert 0
