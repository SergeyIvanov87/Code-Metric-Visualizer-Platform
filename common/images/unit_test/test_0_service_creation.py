#!/usr/bin/python

import os
import pathlib
import pytest
import stat

from settings import Settings
from utils import get_api_queries
from utils import compose_api_queries_pipe_names

global_settings = Settings()
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())

@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_nodes(name, query):
    global global_settings

    # compose expected pipe names, based on query data
    pipes = compose_api_queries_pipe_names(global_settings.api_dir, query)

    # check that special files are really pipes
    for p in pipes:
        assert stat.S_ISFIFO(os.stat(p).st_mode)

11111111111111111
${OPT_DIR}/build_api_executors.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}
${OPT_DIR}/build_api_services.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}/services
${OPT_DIR}/build_api_pseudo_fs.py ${WORK_DIR}/API ${SHARED_API_DIR}

11111111111111111
