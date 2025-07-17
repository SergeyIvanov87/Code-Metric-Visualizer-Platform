#!/usr/bin/python

import os
import pytest
import requests
import shutil
import service_tester_utils
import time

from settings import Settings
from time_utils import get_timestamp
from utils import get_api_queries
from utils import get_files

global_settings = Settings()
testdata = list(get_api_queries(os.path.join(global_settings.work_dir, "restored_API"), global_settings.domain_name_api_entry).items())

def execute_query(name, query):
    global global_settings

    iteration_number=0
    wait_for_restart_iteration_limit=30
    while not service_tester_utils.ping_service("rest_api", 5000) and iteration_number <= wait_for_restart_iteration_limit:
        print(f"{get_timestamp()}\tWaiting for service up, iteration: {iteration_number}/{wait_for_restart_iteration_limit}")
        time.sleep(1)
        iteration_number+=1

    url = 'http://rest_api:5000/' + query["Query"]
    headers = {'Accept-Charset': 'UTF-8'}
    match query["Method"].lower():
        case "get":
            resp = requests.get(url, headers=headers)
        case "put":
            resp = requests.put(url, data=query["Params"], headers=headers)
        case "post":
            resp = requests.post(url, data=query["Params"], headers=headers)
    print(f"{get_timestamp()}\tsent query: {url}, response status: {resp.status}")
    assert resp.ok

@pytest.mark.parametrize("name,query", testdata)
def test_api_queries_lietening(name, query):
    print(f"{get_timestamp()}\tExecute test: {name}")
    global global_settings

    execute_query(name,query)
