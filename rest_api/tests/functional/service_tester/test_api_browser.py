"""Check the browser pages served by the Compose rest-api instance."""

from html.parser import HTMLParser
import json
from pathlib import Path

import pytest
import requests

from settings import Settings
from api_browser_utils import service_name, service_page_url, query_page_url


BASE_URL = "http://rest-api:5000"
DOMAIN = Settings().domain_name_api_entry
QUERIES = [json.loads(source.read_text())
           for source in sorted((Path(Settings().work_dir) / "data").glob("req_*.json"))]
SERVICES = sorted({service_name(query["Query"], DOMAIN) for query in QUERIES} - {None})


class Page(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.links = []
        self.inputs = {}
        self.form = {}
        self.execute_link = None
        self.feed(content)

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == "a":
            self.links.append(attributes.get("href", ""))
            if attributes.get("id") == "execute-query":
                self.execute_link = attributes["href"]
        elif tag == "input" and attributes.get("type") == "text":
            self.inputs[attributes["name"]] = attributes["value"]
        elif tag == "form":
            self.form = attributes


def page_at(path):
    response = requests.get(BASE_URL + path, timeout=10)
    response.raise_for_status()
    return Page(response.text)


def query_pages(service):
    listing = page_at(service_page_url(service, DOMAIN))
    return [page_at(link) for link in sorted(set(listing.links))
            if "/_browse/queries/" in link]


def query_page(query):
    return page_at(query_page_url(query["Query"], query["Method"], DOMAIN))


def test_portal_lists_service_containers():
    portal = page_at("/")
    expected = {service_page_url(service, DOMAIN) for service in SERVICES}
    expected.update(query_page_url(query["Query"], query["Method"], DOMAIN)
                    for query in QUERIES if service_name(query["Query"], DOMAIN) is None)
    assert set(portal.links) == expected


@pytest.mark.parametrize("service", SERVICES)
def test_service_links_lead_to_its_api_pages(service):
    expected = {(query["Method"], "/" + query["Query"]) for query in QUERIES
                if service_name(query["Query"], DOMAIN) == service}
    assert {(page.form["data-method"], page.form["action"])
            for page in query_pages(service)} == expected


@pytest.mark.parametrize("query", QUERIES, ids=lambda query: query["Method"])
def test_query_page_has_parameter_fields_and_execution_link(query):
    page = query_page(query)
    assert page.inputs == query["Params"]
    assert page.execute_link == page.form["action"] == "/" + query["Query"]
    assert page.form["data-method"] == query["Method"]


@pytest.mark.parametrize("query", QUERIES, ids=lambda query: query["Method"])
def test_execute_query_with_edited_field_values(query):
    page = query_page(query)
    fields = page.inputs.copy()
    value = 'edited space &plus+ ä "quoted" \\value'
    fields["param_1"] = value
    result = requests.request(page.form["data-method"], BASE_URL + page.execute_link,
                              params=fields, timeout=30)
    result.raise_for_status()
    assert value in result.text


@pytest.mark.parametrize("query", QUERIES, ids=lambda query: query["Method"])
@pytest.mark.parametrize("submission", ["default-option", "unchanged-form"])
def test_default_preserves_parameter_file_quotes_and_backslashes(query, submission):
    if submission == "unchanged-form":
        page = query_page(query)
        # The rendered fields remain unchanged, so the browser sends no overrides.
        parameters = {}
        method, action = page.form["data-method"], page.execute_link
    else:
        parameters = {"default": ""}
        method, action = query["Method"], "/" + query["Query"]
    result = requests.request(method, BASE_URL + action, params=parameters, timeout=30)
    result.raise_for_status()
    for value in query["Params"].values():
        assert value in result.text
