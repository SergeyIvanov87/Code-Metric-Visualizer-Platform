#!/usr/bin/python

import json
import os
import pathlib
import pytest
import stat
import glob, shutil
import sys

from time_utils import get_timestamp
from settings import Settings
from utils import get_api_queries
from api_deps_utils import get_api_service_dependencies
from api_deps_utils import get_api_service_dependency_files
from api_fs_conventions import compose_api_fs_request_location_paths
from api_fs_query import APIQuery
from api_schema_utils import compose_api_queries_pipe_names
from api_schema_utils import file_extension_from_content_type_or_default
from queries import FS_API_Executor

global_settings = Settings()
innerapi_testdata=[]
executor=None
if os.path.isdir("/API/deps"):
    innerapi_testdata = list(get_api_queries("/API/deps", global_settings.domain_name_api_entry).items())
    executor = FS_API_Executor("/API/deps", global_settings.api_dir, global_settings.domain_name_api_entry)

service_api_deps = get_api_service_dependencies("/API/deps", r".*", r".*\.json$")

def check_all_dependencies_api(query, pipes):
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

def check_unmet_dependencies_api(query, pipes):
    print(f"{get_timestamp()}\tinitiate test query: {query["Query"]}")
    api_query = APIQuery(pipes)
    api_query.execute()


    print(f"{get_timestamp()}\tgetting result of query: {query["Query"]}")
    before_deps_json_str = api_query.wait_result("", 0.1, 30, True)
    before_json_obj = None

    global global_settings
    if len(before_deps_json_str):
        before_json_obj = json.loads(before_deps_json_str)

    # remove some existing API result pipes
    service_api_deps = get_api_service_dependencies("/API/deps", r".*", r".*\.json$")
    for dep_on_service, dep_request_schemas in service_api_deps.items():
        for req_name, req_schema in dep_request_schemas.items():
            print(f"{get_timestamp()}\texclude pipes of query: {req_schema["Query"]} from API fs to simulate unmet deps")
            req_type = req_schema["Method"]
            req_api = req_schema["Query"]

            result_pipe_ext = file_extension_from_content_type_or_default(req_schema,"")
            api_req_directory, api_exec_node_directory = compose_api_fs_request_location_paths(
                "/api", req_api, req_type)

            temporary_replaced_result_pipe_file_path = os.path.join(api_exec_node_directory, "../")
            pipes_to_move_search_glob = ("result." + result_pipe_ext + "*") if result_pipe_ext != "" else "result*"
            for file in glob.glob(os.path.join(api_exec_node_directory,pipes_to_move_search_glob)):
                print(f"{get_timestamp()}\tmove pipe {file} temporary to a new place {temporary_replaced_result_pipe_file_path}")
                try:
                    shutil.move(file, temporary_replaced_result_pipe_file_path)
                except Exception as ex:
                    print(f"{get_timestamp()}\tmove pipe {file} temporary to a new place {temporary_replaced_result_pipe_file_path}, exception: {str(ex)}")

            # removed API service must be unmet

            api_query.execute()

            print(f"{get_timestamp()}\tgetting result of sebsequent query: {query["Query"]}")
            after_deps_json_str = api_query.wait_result("", 0.1, 30, True)

            print(f"{get_timestamp()}\tretrieve pipes of query: {req_schema['Query']} into API fs back")
            for file in glob.glob(os.path.join(temporary_replaced_result_pipe_file_path, pipes_to_move_search_glob)):
                print(f"{get_timestamp()}\tmove pipe {file} back to an old place {api_exec_node_directory}")
                shutil.move(file, api_exec_node_directory)

            assert len(after_deps_json_str)

            after_deps_json_str = after_deps_json_str.rstrip()
            expected = False
            try:
                after_deps_json_obj = json.loads(after_deps_json_str)
                assert len(after_deps_json_obj.keys()) != 0
                assert dep_on_service in after_deps_json_obj.keys()
                assert req_name in after_deps_json_obj[dep_on_service].keys()
                expected = True
            except Exception as e:
                print(f"Exception: {e}", file=sys.stdout, flush=True)
                expected = False
            assert expected
    # retrieve deleted API

    # removed API service must be met
#    finally:
#        shutil.rmtree(temporary_service_api_dir)


@pytest.mark.parametrize("name,query", innerapi_testdata)
def test_inner_api(name, query):
    global global_settings

    # compose expected pipe names, based on query data
    pipes = compose_api_queries_pipe_names(global_settings.api_dir, query)

    if name == "all_dependencies":
        check_all_dependencies_api(query, pipes)
    elif name == "unmet_dependencies":
        check_unmet_dependencies_api(query, pipes)
    else:
        assert 0
