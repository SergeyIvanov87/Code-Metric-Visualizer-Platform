#!/usr/bin/python

#!/usr/bin/python

import os
import pathlib
import pytest
import stat

from settings import Settings
from utils import get_api_queries
from api_schema_utils import compose_api_queries_pipe_names

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
