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
RESPONSE_QUERIES = [json.loads(source.read_text())
                    for source in sorted((Path(Settings().work_dir) / "data").glob("response_*.json"))]
SERVICES = sorted({service_name(query["Query"], DOMAIN) for query in QUERIES} - {None})


class Page(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.links = []
        self.headings = []
        self.heading_parts = None
        self.inputs = {}
        self.form = {}
        self.execute_link = None
        self.feed(content)

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag in {"h1", "h2", "h3"}:
            self.heading_parts = []
        if tag == "a":
            self.links.append(attributes.get("href", ""))
            if attributes.get("id") == "execute-query":
                self.execute_link = attributes["href"]
        elif tag == "input" and attributes.get("type") == "text":
            self.inputs[attributes["name"]] = attributes["value"]
        elif tag == "form":
            self.form = attributes

    def handle_data(self, data):
        if self.heading_parts is not None:
            self.heading_parts.append(data)

    def handle_endtag(self, tag):
        if tag in {"h1", "h2", "h3"} and self.heading_parts is not None:
            self.headings.append("".join(self.heading_parts).strip())
            self.heading_parts = None


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
    expected = {(query["Method"], "/" + query["Query"]) for query in QUERIES + RESPONSE_QUERIES
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


@pytest.mark.parametrize("service", ["cyclomatic_complexity", "rrd_analytic"])
def test_service_root_endpoint_belongs_to_its_container(service):
    assert service_name(DOMAIN + "/" + service, DOMAIN) == service


def test_single_component_fixture_is_grouped_on_portal():
    portal = page_at("/")
    assert "/" + DOMAIN + "/_browse/services/req_1" in portal.links
    listing = page_at("/" + DOMAIN + "/_browse/services/req_1")
    query = next(query for query in QUERIES if query["Query"] == DOMAIN + "/req_1")
    assert query_page_url(query["Query"], query["Method"], DOMAIN) in listing.links


@pytest.mark.parametrize("source", sorted((Path(Settings().work_dir) / "data").glob("req_*.json")), ids=lambda source: source.stem)
def test_service_keeps_readme_names_without_repeated_query_path_headings(source):
    query = json.loads(source.read_text())
    page = page_at(service_page_url(service_name(query["Query"], DOMAIN), DOMAIN))
    assert source.stem in page.headings
    assert all(query["Query"] not in heading for heading in page.headings)
    assert page.links.count(query_page_url(query["Query"], query["Method"], DOMAIN)) == 1
