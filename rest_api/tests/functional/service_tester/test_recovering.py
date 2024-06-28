#!/usr/bin/python

import os
import pytest
import requests
import shutil
import time
import service_tester_utils

from api_schema_utils import deserialize_api_request_from_schema_file
from settings import Settings
from utils import get_api_queries
from utils import get_files
from utils import get_api_schema_files

from make_api_readme import make_api_readme

global_settings = Settings()
testdata = list(get_api_queries(os.path.join(global_settings.work_dir, "restored_API"), global_settings.domain_name_api_entry).items())

def check_if_query_available(domain, query):
    global global_settings

    #url = 'http://rest_api:5000/' + query["Query"]
    url = 'http://rest_api:5000/' + domain
    headers = {'Accept-Charset': 'UTF-8'}
    resp = requests.get(url, headers=headers)
    assert resp.ok
    readme_html_content = str(resp.text)
    return readme_html_content.find(query["Query"]) != -1


@pytest.fixture()
def all_api_query_files():
    global global_settings
    return get_api_schema_files(os.path.join(global_settings.work_dir, "restored_API"))

def tear_down(main_readme_file, main_query_file):
    print(f"retrieve back {main_query_file}")
    shutil.move(main_query_file + "_bk", main_query_file)
    print(f"retrieve back {main_readme_file}")
    shutil.move(main_readme_file + "_bk", main_readme_file)

@pytest.mark.parametrize("name_query_2_turn_off,query_2_turn_off", testdata)
def test_api_queries_lietening(name_query_2_turn_off, query_2_turn_off, all_api_query_files):
    shared_api_dir = os.getenv('SHARED_API_DIR', '/api')
    main_service_name = os.getenv('MAIN_SERVICE_NAME', 'api.pmccabe_collector.restapi.org')

    # backup initial readme, which is used for backing an entrypoint of REST_API
    initial_readme_file = os.path.join(shared_api_dir, main_service_name, "README-API-MOCK.md")
    shutil.copy(initial_readme_file, initial_readme_file + "_bk")
    print(f"Execute test: {name_query_2_turn_off}. original README: {initial_readme_file}")
    global global_settings

    # remove query from `restored_API` and regenerate new initial_readme_file without that query
    query_to_disable_file=""
    for query_file in all_api_query_files:
        name_query, query = deserialize_api_request_from_schema_file(query_file)
        if name_query == name_query_2_turn_off:
            with open(initial_readme_file, "w") as mock_readme_stream:
                query_to_disable_file = query_file
                print (f"temporary remove the schema file: {query_to_disable_file} to the new place: {query_to_disable_file + '_bk'}")
                shutil.move(query_to_disable_file, query_to_disable_file + "_bk")
                make_api_readme(os.path.join(global_settings.work_dir, "restored_API"), mock_readme_stream)
            break
    assert len(query_to_disable_file)

    stopped, started = service_tester_utils.if_service_reconfigured("rest_api", 5000, 10, 30, 1)
    assert stopped
    assert started

    turned_off_query_result = check_if_query_available("api.pmccabe_collector.restapi.org", query_2_turn_off)
    if turned_off_query_result:
        print(f"Service must not serve query anymore: ${name_query_2_turn_off}. Test ${name_query_2_turn_off} failed!")
        tear_down(initial_readme_file, query_to_disable_file)
        assert not turned_off_query_result

    # retrieve all disabled queries
    os.remove(initial_readme_file)
    tear_down(initial_readme_file, query_to_disable_file)

    stopped, started = service_tester_utils.if_service_reconfigured("rest_api", 5000, 10, 30, 1)
    assert stopped
    assert started

    expected_query_result = check_if_query_available("api.pmccabe_collector.restapi.org", query_2_turn_off)
    if not expected_query_result:
        print(f"Service must serve query: ${name_query_2_turn_off} after its retrieval. Test ${name_query_2_turn_off} failed!")
        assert expected_query_result
