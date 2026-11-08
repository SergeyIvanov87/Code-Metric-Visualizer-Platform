"""Exercise real Envoy routing with REST after a different catch-all provider."""
import os
import time
from urllib.parse import urlsplit

import pytest
import requests

from api_browser_utils import query_page_url
from test_api_browser import DOMAIN, Page, QUERIES


GATEWAY = os.environ.get("REST_API_GATEWAY_URL")
pytestmark = pytest.mark.skipif(not GATEWAY, reason="Requires compose-routing.test.yaml overlay")


@pytest.fixture(scope="module", autouse=True)
def gateway_ready():
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            response = requests.get(GATEWAY + "/not-advertised", timeout=2)
            if response.ok and response.json().get("backend") == "fallback":
                return
        except (requests.RequestException, ValueError):
            pass
        time.sleep(0.25)
    pytest.fail("Envoy did not become ready with the first provider as fallback")


@pytest.mark.parametrize("query", QUERIES, ids=lambda query: query["Method"])
def test_form_and_execution_reach_action_owner_through_gateway(query):
    form_url = query_page_url(query["Query"], query["Method"], DOMAIN)
    assert urlsplit(form_url).path == "/" + query["Query"]
    response = requests.get(GATEWAY + form_url, timeout=10)
    response.raise_for_status()
    page = Page(response.text)
    assert page.form["data-method"] == query["Method"]
    assert page.form["action"] == "/" + query["Query"]
    assert page.execute_link == page.form["action"]
    # The action URL carries no view selector and executes the declared method.
    result = requests.request(page.form["data-method"], GATEWAY + page.form["action"],
                              params={"param_1": "via gateway & edited"}, timeout=30)
    result.raise_for_status()
    assert "via gateway & edited" in result.text


def test_form_assets_reach_same_owner_without_fallback():
    query = QUERIES[0]
    response = requests.get(GATEWAY + query_page_url(query["Query"], query["Method"], DOMAIN), timeout=10)
    response.raise_for_status()
    page = Page(response.text)
    assert len(page.assets) == 2
    for asset in page.assets:
        assert urlsplit(asset).path == "/" + query["Query"]
        result = requests.get(GATEWAY + asset, timeout=10)
        result.raise_for_status()
        assert not result.headers["Content-Type"].startswith("application/json")
        assert "json-formatter" in result.text.lower() or "JSONFormatter" in result.text


def test_post_only_browser_redirect_preserves_advertised_path():
    query = next(query for query in QUERIES if query["Method"] == "POST")
    response = requests.get(GATEWAY + "/" + query["Query"], allow_redirects=False, timeout=10)
    assert response.status_code == 302
    location = response.headers["Location"]
    assert location == query_page_url(query["Query"], "POST", DOMAIN)
    assert urlsplit(location).path == "/" + query["Query"]
    page = requests.get(GATEWAY + location, timeout=10)
    page.raise_for_status()
    assert Page(page.text).form["data-method"] == "POST"
