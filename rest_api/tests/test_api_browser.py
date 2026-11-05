"""Exercise generated navigation and handlers together, without live services."""

import io
import os
import stat
import subprocess
import sys
from types import SimpleNamespace

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file
import markdown
import pytest

from test_build_api_cgi import (
    COMMON_DIRECTORY, FakeLogger, REPOSITORY_ROOT, TEST_DIRECTORY,
    generate_cgi, generate_from_directory,
)


DOMAIN = "api.pmccabe_collector.restapi.org"
TEMPLATES = REPOSITORY_ROOT / "rest_api/rest_api_server/rest_api_server/templates"
if not TEMPLATES.is_dir():
    TEMPLATES = TEST_DIRECTORY / "templates"


def schema(service, method="GET", params=None):
    return {"Query": f"{DOMAIN}/{service}/query", "Method": method,
            "Content-Type": "text/plain", "Params": params or {}}


def load_browser(generated, query_type=None):
    app = Flask(__name__, template_folder=str(TEMPLATES))
    app.testing = True

    class UnexpectedQuery:
        def __init__(self, *_args, **_kwargs):
            pytest.fail("Browsing must not construct a filesystem query")

    namespace = {
        "app": app, "abort": abort, "jsonify": jsonify,
        "redirect": redirect, "render_template": render_template,
        "request": request, "send_file": send_file, "markdown": markdown,
        "APIQuery": query_type or UnexpectedQuery,
        "APIQueryInterruptible": query_type or UnexpectedQuery,
        "socket": SimpleNamespace(gethostname=lambda: "server",
                                  gethostbyaddr=lambda _address: ("client", [], [])),
        "os": SimpleNamespace(path=SimpleNamespace(exists=lambda _path: True),
                              stat=lambda _path: SimpleNamespace(st_mode=stat.S_IFIFO)),
        "stat": stat, "io": io, "docker_logger": FakeLogger(),
        "queries_in_progress": 0,
    }
    exec(compile(generated, "<generated-cgi>", "exec"), namespace)
    return app.test_client(), namespace


def test_navigation_groups_services_and_never_executes_queries(tmp_path):
    schemas = {"alpha_get": schema("alpha"), "alpha_put": schema("alpha", "PUT"),
               "beta_post": schema("beta", "POST")}
    client, namespace = load_browser(generate_cgi(tmp_path, schemas))
    assert client.get("/").location == "/" + DOMAIN
    landing = client.get("/" + DOMAIN).get_data(as_text=True)
    assert landing.count('>alpha</a>') == 1
    assert landing.count('>beta</a>') == 1
    assert "/alpha/query" not in landing
    alpha = namespace["BROWSER_SERVICES"]["alpha"]
    listing = client.get(alpha["url"]).get_data(as_text=True)
    assert "beta" not in listing
    for query in alpha["queries"]:
        assert f'href="{query["page_url"]}"' in listing
        assert f'href="{query["action_url"]}"' not in listing
        page = client.get(query["page_url"])
        assert page.status_code == 200
        assert f'data-method="{query["method"]}"' in page.get_data(as_text=True)
    beta = namespace["BROWSER_SERVICES"]["beta"]["queries"][0]
    assert client.get(beta["page_url"]).status_code == 200
    assert client.get(beta["action_url"]).location == beta["page_url"]
    assert client.get("/" + DOMAIN + "/_browse/services/missing").status_code == 404
    assert client.get("/" + DOMAIN + "/_browse/queries/missing").status_code == 404
    assert client.post(beta["page_url"]).status_code == 405


def test_forms_include_inherited_defaults_and_escape_html(tmp_path):
    params = {"parent": {"inherited": "a & b + c", "shared": "parent"},
              "shared": "local", 'name"<': '"><script>alert(1)</script>',
              "empty": "", "enabled": True, "optional": None,
              "SESSION_ID": "cannot-override-session"}
    client, namespace = load_browser(generate_cgi(tmp_path, {"query": schema("alpha", params=params)}))
    query = next(iter(namespace["BROWSER_QUERIES"].values()))
    page = client.get(query["page_url"]).get_data(as_text=True)
    assert 'name="inherited" value="a &amp; b + c"' in page
    assert 'name="shared" value="local"' in page
    assert 'name="empty" value=""' in page
    assert "&lt;script&gt;" in page
    assert "<script>alert(1)</script>" not in page
    assert "cannot-override-session" not in page
    assert 'name="parent"' not in page


@pytest.mark.parametrize("method", ["GET", "PUT", "POST"])
def test_execution_forwards_only_declared_parameters_and_preserves_method(tmp_path, method):
    commands = []

    class Query:
        def __init__(self, *_args, **_kwargs):
            pass

        def is_valid(self):
            return True

        def execute(self, command):
            commands.append((request.method, command))

        def wait_binary_result(self, *_args):
            return b"result from service"

    client, namespace = load_browser(generate_cgi(tmp_path, {
        "query": schema("alpha", method, {"parent": {"inherited": "default"}, "local": "default"}),
    }), Query)
    query = next(iter(namespace["BROWSER_QUERIES"].values()))
    response = client.open(query["action_url"], method=method, query_string={
        "local": "changed", "inherited": "a&b+c", "unknown": "ignored", "SESSION_ID": "ignored",
    })
    assert response.status_code == 200
    assert response.data == b"result from service"
    assert response.mimetype == "text/plain"
    assert commands == [(method, f'SESSION_ID={method}_server_client inherited="a&b+c" local="changed"')]
    assert namespace["queries_in_progress"] == 0
    response = client.open(query["action_url"], method=method, query_string={"default": ""})
    assert response.status_code == 200
    assert commands[-1] == (method, f"SESSION_ID={method}_server_client inherited=default local=default")
    invalid = client.open(query["action_url"], method=method, query_string={"local": "first\nsecond"})
    assert invalid.status_code == 400
    assert len(commands) == 2
    assert namespace["queries_in_progress"] == 0


def test_service_documentation_links_open_forms(tmp_path):
    query = schema("alpha")
    readme = f'## Alpha query\n\n### {query["Query"]}/GET [execute](/{query["Query"]})\n\nOriginal documentation.\n'
    client, namespace = load_browser(generate_cgi(tmp_path, {"query": query}, readme))
    entry = next(iter(namespace["BROWSER_QUERIES"].values()))
    listing = client.get(entry["service_url"]).get_data(as_text=True)
    assert "Original documentation." in listing
    assert f'href="{entry["page_url"]}"' in listing
    assert f'href="{entry["action_url"]}"' not in listing


@pytest.mark.parametrize("readme", ["", f'## Alpha\n\n### {DOMAIN}/alpha/query/GET\n\nPublished API.\n'])
def test_readme_withdrawal_hides_queries_while_preserving_direct_routes(tmp_path, readme):
    schemas = {"alpha": schema("alpha"), "beta": schema("beta")}
    client, namespace = load_browser(generate_cgi(tmp_path, schemas, readme))
    assert set(namespace["BROWSER_SERVICES"]) == ({"alpha"} if readme else set())
    assert client.get(f"/{DOMAIN}/_browse/services/beta").status_code == 404
    paths = {route["path"] for route in client.get("/.well-known/http-api-routes/v1").json["routes"]}
    assert f"/{DOMAIN}/beta/query" in paths


def test_same_path_methods_have_separate_forms_and_one_discovery_route(tmp_path):
    client, namespace = load_browser(generate_cgi(tmp_path, {
        method: schema("alpha", method) for method in ["GET", "PUT", "POST"]
    }))
    entries = list(namespace["BROWSER_QUERIES"].values())
    assert len({entry["page_url"] for entry in entries}) == 3
    for entry in entries:
        assert client.get(entry["page_url"]).status_code == 200
    discovery = client.get("/.well-known/http-api-routes/v1").json
    assert discovery["routes"] == [{"path": f"/{DOMAIN}/alpha/query", "timeout_seconds": 60}]


def test_browser_rebuild_removes_disappeared_services_and_queries(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir()
    after.mkdir()
    _, old = load_browser(generate_cgi(before, {"alpha": schema("alpha"), "beta": schema("beta")}))
    client, new = load_browser(generate_cgi(after, {"alpha": schema("alpha")}))
    beta = old["BROWSER_SERVICES"]["beta"]
    assert client.get(beta["url"]).status_code == 404
    assert client.get(beta["queries"][0]["page_url"]).status_code == 404
    assert set(new["BROWSER_SERVICES"]) == {"alpha"}


def test_forms_use_parameters_recovered_from_filesystem(tmp_path):
    mount = tmp_path / "api"
    service = mount / DOMAIN / "alpha"
    operation = service / "query"
    method = operation / "GET"
    method.mkdir(parents=True)
    (service / "0.inherited").write_text("inherited default")
    (operation / "0.local").write_text("local default")
    (service / "README.md").write_text(f"## Query\n\n### {DOMAIN}/alpha/query/GET\n\nRecovered docs.\n")
    os.mkfifo(method / "exec")
    os.mkfifo(method / "result.txt")
    recovered = tmp_path / "recovered"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join([str(COMMON_DIRECTORY), str(COMMON_DIRECTORY / "modules")])
    subprocess.run([sys.executable, str(COMMON_DIRECTORY / "restore_api_from_pseudo_fs.py"),
                    str(mount), DOMAIN, str(recovered)], check=True, env=environment, capture_output=True)
    client, namespace = load_browser(generate_from_directory(recovered))
    entry = next(iter(namespace["BROWSER_QUERIES"].values()))
    page = client.get(entry["page_url"]).get_data(as_text=True)
    assert 'name="inherited" value="inherited default"' in page
    assert 'name="local" value="local default"' in page
    assert "Recovered docs." in page
