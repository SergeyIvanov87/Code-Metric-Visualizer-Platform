#!/usr/bin/python

import os
import pytest
import requests
import shutil
import time
from api_browser_utils import service_name, service_page_url

from api_schema_utils import deserialize_api_request_from_schema_file
from settings import Settings
from time_utils import get_timestamp
from utils import get_api_queries
from utils import get_files
from utils import get_api_schema_files

from make_api_readme import make_api_readme

global_settings = Settings()
# portal.json is synthetic tester documentation, not a discovered FIFO query.
# The portal itself now lists service containers rather than README entries.
testdata = [
    (name, query)
    for name, query in get_api_queries(os.path.join(global_settings.work_dir, "restored_API"), global_settings.domain_name_api_entry).items()
    if query["Query"] != global_settings.domain_name_api_entry
]

def check_if_query_available(domain, query):
    global global_settings

    url = 'http://rest-api:5000' + service_page_url(service_name(query["Query"], domain), domain)
    headers = {'Accept-Charset': 'UTF-8'}
    resp = requests.get(url, headers=headers, timeout=5)
    if resp.status_code == 404:
        return False
    assert resp.ok
    readme_html_content = str(resp.text)
    return readme_html_content.find(query["Query"]) != -1


def wait_for_query_visibility(domain, query, expected, timeout=30):
    # A fast restart need not be observable by a periodic HEAD probe. Wait for
    # the published API state, rather than requiring an availability outage.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if check_if_query_available(domain, query) == expected:
                return True
        except requests.RequestException:
            pass  # A connection failure alone does not establish publication.
        time.sleep(0.2)
    return False


@pytest.fixture()
def all_api_query_files():
    global global_settings
    return get_api_schema_files(os.path.join(global_settings.work_dir, "restored_API"))

def tear_down(main_readme_file, main_query_file):
    print(f"{get_timestamp()}\tretrieve back {main_query_file}")
    shutil.move(main_query_file + "_bk", main_query_file)
    print(f"{get_timestamp()}\tretrieve back {main_readme_file}")
    shutil.move(main_readme_file + "_bk", main_readme_file)

@pytest.mark.parametrize("name_query_2_turn_off,query_2_turn_off", testdata)
def test_api_queries_lietening(name_query_2_turn_off, query_2_turn_off, all_api_query_files):
    shared_api_dir = os.getenv('SHARED_API_DIR', '/api')
    main_service_name = os.getenv('MAIN_SERVICE_NAME', 'api.pmccabe_collector.restapi.org')

    # backup initial readme, which is used for backing an entrypoint of REST_API
    initial_readme_file = os.path.join(shared_api_dir, main_service_name, "README-API-MOCK.md")
    shutil.copy(initial_readme_file, initial_readme_file + "_bk")
    print(f"{get_timestamp()}\tExecute test: {name_query_2_turn_off}. original README: {initial_readme_file}")
    global global_settings

    # remove query from `restored_API` and regenerate new initial_readme_file without that query
    query_to_disable_file=""
    for query_file in all_api_query_files:
        name_query, query = deserialize_api_request_from_schema_file(query_file)
        if name_query == name_query_2_turn_off:
            with open(initial_readme_file, "w") as mock_readme_stream:
                query_to_disable_file = query_file
                print (f"{get_timestamp()}\ttemporary remove the schema file: {query_to_disable_file} to the new place: {query_to_disable_file + '_bk'}")
                shutil.move(query_to_disable_file, query_to_disable_file + "_bk")
                make_api_readme(os.path.join(global_settings.work_dir, "restored_API"), mock_readme_stream)
            break
    assert len(query_to_disable_file)

    try:
        assert wait_for_query_visibility(main_service_name, query_2_turn_off, False)
    finally:
        # Restore fixtures even if withdrawal fails, so later cases stay isolated.
        os.remove(initial_readme_file)
        tear_down(initial_readme_file, query_to_disable_file)

    assert wait_for_query_visibility(main_service_name, query_2_turn_off, True)
