#!/usr/bin/python

import os
import pytest
import requests
import shutil

from settings import Settings
from utils import get_api_queries
from utils import get_files

global_settings = Settings()
testdata = list(get_api_queries(os.path.join(global_settings.work_dir, "restored_API"), global_settings.domain_name_api_entry).items())

def execute_query(name, query):
    global global_settings

    url = 'http://rest_api:5000/' + query["Query"]
    headers = {'Accept-Charset': 'UTF-8'}
    match query["Method"].lower():
        case "get":
            resp = requests.get(url, headers=headers)
        case "put":
            resp = requests.put(url, data=query["Params"], headers=headers)
        case "post":
            resp = requests.post(url, data=query["Params"], headers=headers)
    assert resp.ok

@pytest.mark.parametrize("name,query", testdata)
def test_api_queries_lietening(name, query):
    print(f"Execute test: {name}")
    global global_settings

    execute_query(name,query)
