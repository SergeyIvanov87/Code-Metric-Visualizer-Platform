#!/usr/bin/python

import os
import pytest
import shutil
import time

from heartbeat import Heartbeat
from settings import Settings
from time_utils import get_timestamp
from utils import get_api_queries
from utils import get_files

file_must_be_created = False
def check_query_counter(req, iteration_count=2):
    last_counter_value=int(0)
    i = 0
    global file_must_be_created
    h = Heartbeat()
    query_response_litmus_test_file="/tmp/test/" + req + ".counter"

    while i < iteration_count:
        try:
            with open(query_response_litmus_test_file, "r") as file:
                counter = int(file.read())
                assert last_counter_value <= counter
                last_counter_value = counter
        except Exception as e:
            assert file_must_be_created == False
            file_must_be_created = True
            h.run(f"Test '{req}' is in progress... Waiting for litmus test file: {query_response_litmus_test_file} creation")
            time.sleep(61)
            h.stop()
            continue
        i += 1
        if i >= iteration_count:
            break
        h.run(f"Test '{req}' is in progress... Waiting for a next job execution, iteration: {i}")
        time.sleep(61)
        h.stop()

    assert last_counter_value > 0


global_settings = Settings()
dep_service_dir_list = [os.path.join("API/deps", d) for d in os.listdir("API/deps") if os.path.isdir(os.path.join("API/deps", d))]

testdata=[]
for service in dep_service_dir_list:
    testdata.extend(list(get_api_queries(os.path.join(global_settings.work_dir, service), global_settings.domain_name_api_entry).items()))

@pytest.mark.parametrize("name, query", testdata)
def test_api_queries_listening(name, query):
    global global_settings
    if name=="all_dependencies" or name=="unmet_dependencies":
        return
    print(f"{get_timestamp()}\tExecute test: {name}")
    check_query_counter(name)
