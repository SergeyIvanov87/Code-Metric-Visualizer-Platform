#!/usr/bin/python

import os
import pytest
import shutil
import time

from settings import Settings
from utils import get_api_queries
from utils import get_files

file_must_be_created = False
def check_query_counter(req, iteration_count=2):
    last_counter_value=int(0)
    i = 0
    global file_must_be_created
    while i < iteration_count:
        try:
            with open(f"/tmp/test/{req}.counter", "r") as file:
                counter = int(file.read())
                assert last_counter_value <= counter
                last_counter_value = counter
        except Exception as e:
            assert file_must_be_created == False
            file_must_be_created = True
            time.sleep(61)
            continue
        i += 1
        if i >= iteration_count:
            break
        time.sleep(61)

    assert last_counter_value > 0


global_settings = Settings()
testdata = list(get_api_queries(os.path.join(global_settings.work_dir, "API"), global_settings.domain_name_api_entry).items())


@pytest.mark.parametrize("name,query", testdata)
def test_api_queries_lietening(name, query):
    global global_settings

    check_query_counter(name)
