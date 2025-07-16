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

if os.path.isdir("/API/deps"):
    testdata.extend(list(get_api_queries("/API/deps", global_settings.domain_name_api_entry).items()))

@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_nodes(name, query):
    global global_settings

    # compose expected pipe names, based on query data
    pipes = compose_api_queries_pipe_names(global_settings.api_dir, query)

    # check that special files are really pipes
    for p in pipes:
        assert stat.S_ISFIFO(os.stat(p).st_mode)

    # check that query directory has no go+w permission
    query_dir = os.path.dirname(pipes[0])
    current = stat.S_IMODE(os.lstat(query_dir).st_mode)
    assert current & (stat.S_IRUSR | stat.S_IXUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IXGRP| stat.S_IROTH | stat.S_IXOTH)
    assert not (current & (stat.S_IWGRP| stat.S_IWOTH))
