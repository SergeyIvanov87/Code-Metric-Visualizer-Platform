import glob
import json
import os

import requests

from settings import Settings


DISCOVERY_URL = "http://rest-api:5000/.well-known/http-api-routes/v1"


def test_discovery_endpoint_lists_all_restored_api_queries():
    settings = Settings()
    expected_paths = set()
    for schema_path in glob.glob(os.path.join(settings.work_dir, "data", "req_*.json")):
        with open(schema_path, encoding="utf-8") as schema_file:
            query = json.load(schema_file)["Query"]
        domain_offset = query.find(settings.domain_name_api_entry)
        if domain_offset >= 0:
            expected_paths.add("/" + query[domain_offset:].lstrip("/"))

    response = requests.get(DISCOVERY_URL, timeout=10)
    response.raise_for_status()
    document = response.json()

    assert document["schema_version"] == 1
    assert document["revision"].startswith("sha256:")
    assert {route["path"] for route in document["routes"]} == expected_paths
    assert all(route["timeout_seconds"] == 60 for route in document["routes"])
