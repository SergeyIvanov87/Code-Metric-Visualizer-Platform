"""Check response metadata and actual payloads through the Compose REST server."""
import json
from pathlib import Path

import pytest
import requests

from api_browser_utils import query_page_url
from settings import Settings
from test_api_browser import Page


@pytest.mark.parametrize("name,kind,extension,content_type,payload", [
    ("text", "text", "txt", "text/plain", b"Plain text <b id=server-markup>response</b>"),
    ("json", "json", "json", "application/json", b'{"auth":true,"message":"<b id=server-markup>JSON</b>"}'),
    ("image", "image", "svg", "image/svg+xml", b'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"><rect width="1200" height="800" fill="steelblue"/></svg>'),
    ("binary", "binary", "bin", "application/octet-stream", b"\x00\x01\xfffixture\n"),
])
def test_response_page_metadata_matches_fifo_payload(name, kind, extension, content_type, payload):
    settings = Settings()
    query = json.loads((Path(settings.work_dir) / "data" / f"response_{name}.json").read_text())
    page_url = query_page_url(query["Query"], query["Method"], settings.domain_name_api_entry)
    page_response = requests.get("http://rest-api:5000" + page_url, timeout=10)
    page_response.raise_for_status()
    form = Page(page_response.text).form
    assert form["data-result-kind"] == kind
    assert form["data-result-extension"] == extension
    response = requests.request(form["data-method"], "http://rest-api:5000" + form["action"], timeout=30)
    response.raise_for_status()
    assert response.headers["Content-Type"].split(";")[0] == content_type
    assert response.content == payload
