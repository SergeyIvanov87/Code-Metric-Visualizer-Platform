"""Follow generated pages and execute the form action against real FIFOs."""

import glob
from html.parser import HTMLParser
import json
import os

import pytest
import requests

from settings import Settings


BASE_URL = "http://rest-api:5000"
DOMAIN = "api.pmccabe_collector.restapi.org"


class Page(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.links = []
        self.inputs = {}
        self.form = {}
        self.feed(content)

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == "a":
            self.links.append(attributes.get("href", ""))
        elif tag == "input":
            self.inputs[attributes["name"]] = attributes["value"]
        elif tag == "form":
            self.form = attributes


@pytest.mark.parametrize("method", ["GET", "PUT", "POST"])
def test_browse_and_execute_with_edited_parameters(method):
    settings = Settings()
    for source in glob.glob(os.path.join(settings.work_dir, "data", "req_*.json")):
        with open(source) as stream:
            query = json.load(stream)
        if query["Method"] == method:
            break
    else:
        pytest.fail(f"No fixture for {method}")
    service_name = query["Query"].split("/", 1)[1].split("/", 1)[0]
    landing = requests.get(f"{BASE_URL}/{DOMAIN}", timeout=10)
    landing.raise_for_status()
    service_link = f"/{DOMAIN}/_browse/services/{service_name}"
    assert service_link in Page(landing.text).links
    service_page = requests.get(BASE_URL + service_link, timeout=10)
    service_page.raise_for_status()
    query_link = next(link for link in Page(service_page.text).links if "/_browse/queries/" in link)
    form_page = requests.get(BASE_URL + query_link, timeout=10)
    form_page.raise_for_status()
    form = Page(form_page.text)
    assert form.form["data-method"] == method
    assert form.inputs == query["Params"]
    value = 'edited space &plus+ ä "quoted" \\value'
    result = requests.request(method, BASE_URL + form.form["action"], params={"param_1": value}, timeout=30)
    result.raise_for_status()
    assert value in result.text
