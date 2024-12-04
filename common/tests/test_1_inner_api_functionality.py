#!/usr/bin/python

import json
import os
import pathlib
import pytest
import stat

from time_utils import get_timestamp
from settings import Settings
from utils import get_api_queries
from api_deps_utils import get_api_service_dependencies
from api_fs_query import APIQuery
from api_schema_utils import compose_api_queries_pipe_names
from queries import FS_API_Executor

global_settings = Settings()
innerapi_testdata=[]
executor=None
if os.path.isdir("/API/deps"):
    innerapi_testdata = list(get_api_queries("/API/deps", global_settings.domain_name_api_entry).items())
    executor = FS_API_Executor("/API/deps", global_settings.api_dir, global_settings.domain_name_api_entry)

service_api_deps = get_api_service_dependencies("/API/deps", r".*", r".*\.json$")

def check_dependencies_api(query, pipes):
    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    api_query = APIQuery(pipes)
    api_query.execute()


    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    json_str = api_query.wait_result("", 0.1, 30, True)
    assert len(json_str)
    try:
        json_obj = json.loads(json_str)
        assert len(json_obj.keys()) != 0
        for service in service_api_deps.keys():
            assert service in json_obj
            assert json_obj[service] == service_api_deps[service]
    except Exception as e:
        assert 0


@pytest.mark.parametrize("name,query", innerapi_testdata)
def test_inner_api(name, query):
    global global_settings

    # compose expected pipe names, based on query data
    pipes = compose_api_queries_pipe_names(global_settings.api_dir, query)

    if name == "dependencies":
        check_dependencies_api(query, pipes)
    else:
        assert 0
