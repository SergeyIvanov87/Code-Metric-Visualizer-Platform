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

    url = 'https://rest_api:5000/' + query["Query"]
    headers = {'Accept-Charset': 'UTF-8'}
    resp = requests.get(url, data=payload, headers=headers)
    print(resp)
    assert resp.ok
'''
{
    "Content-Type" : "image/svg+xml",
    "Method" : "GET",
    "Query": "api.pmccabe_collector.restapi.org/cc/statistic/view/flamegraph",
    "Params": {
        "view" : {
            "statistic" : {
                "watch_list" : {
                    "-regex": "\".*\\.\\(hpp\\|cpp\\|c\\|h\\)\"",
                    "-prune": "! -path \"*buil*\" ! -path \"*thirdpart*\""
                },
                "-mmcc" : "1,",
                "-tmcc" : "1,",
                "-sif" : "1,",
                "-lif" : "1,"
            },
            "-attr" : "mmcc,tmcc,sif,lif"
        },
        "--width": "1200",
        "--height" : "16"
    },
    "Description": {
        "header": "Generates visual representation of various cyclomatic compexity metrics of the project in the flamegraph format.\nFor more information about flamegraph, please refer https://github.com/brendangregg/FlameGraph#3-flamegraphpl",
        "body": "To make a query:\n\n`echo \"0\" > api.pmccabe_collector.restapi.org/cc/statistic/view/flamegraph/GET/exec`\n\nTo wait and extract the query result:\n\n`cat api.pmccabe_collector.restapi.org/cc/statistic/view/flamegraph/GET/result.svg > <your_filename>.svg`\n\n",
        "footer": "Please pay attention that a flamegraph collected in `*.svg` format is interactive in exploration. To leverage that navigation through a call stack please open this file in any web-browser."
    }
}

'''

@pytest.mark.parametrize("name,query", testdata)
def test_api_queries_lietening(name, query):
    global global_settings

    execute_query(name,query)
