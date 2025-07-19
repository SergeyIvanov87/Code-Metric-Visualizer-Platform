#!/usr/bin/python

import os
import pytest
import requests
import shutil
import socket

import service_tester_utils

from heartbeat import Heartbeat
from settings import Settings
from time_utils import get_timestamp
from utils import get_api_queries
from utils import get_files

global_settings = Settings()
testdata = list(get_api_queries(os.path.join(global_settings.work_dir, "API_for_testing"), global_settings.domain_name_api_entry).items())

def execute_query(name, query):
    global global_settings

    url = 'http://rest_api:5000/' + query["Query"]
    headers = {'Accept-Charset': 'UTF-8'}

    print(f"{get_timestamp()}\tsend query: {url}")
    params = query["Params"]
    params["SESSION_ID"] = socket.gethostname() + "_" + name

    service_is_up = False
    while not service_is_up:
        h = Heartbeat()
        h.run(f"{get_timestamp()}\tTest 'execute_query: {query['Query']}' is in progress, waiting for a service up...")
        service_is_up = service_tester_utils.if_service_started_up_until("rest_api", 5000, 60, 1)
        h.stop()
        assert service_is_up

        match query["Method"].lower():
            case "get":
                resp = requests.get(url, data=params, headers=headers)
            case "put":
                resp = requests.put(url, data=params, headers=headers)
            case "post":
                resp = requests.post(url, data=params, headers=headers)
        print(f"{get_timestamp()}\tsent query: {url}, response status: {resp.content if not resp.ok else '<not an error, ignored>'}")
        service_is_up = service_tester_utils.ping_service("rest_api", 5000)
        print(f"resp: {resp.ok}, service_is_up: {service_is_up}")
        assert resp.ok or not service_is_up


@pytest.mark.parametrize("name,query", testdata)
def test_api_queries_listening(name, query):
    print(f"{get_timestamp()}\tExecute test: {name}")
    global global_settings

    execute_query(name,query)
