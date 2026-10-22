"""Opt-in real HTTP integration: ENVOY_BINARY=/path/to/envoy pytest ..."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

from flask import Flask, jsonify, request
import pytest
from werkzeug.serving import make_server
import yaml


@contextmanager
def http_server(app):
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.fixture
def routed_http(app, tmp_path):
    binary = os.environ.get("ENVOY_BINARY")
    if not binary:
        pytest.skip("Set ENVOY_BINARY to enable real Envoy HTTP tests")
    generic = Flask("generic-rest-api-stub")
    @generic.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT"])
    @generic.route("/<path:path>", methods=["GET", "POST", "PUT"])
    def generic_query(path):
        return jsonify(backend="generic", path=request.path, method=request.method, query=request.query_string.decode(), body=request.get_data().decode())
    repo = Path(__file__).resolve().parents[3]
    config = yaml.safe_load((repo / "fs_api_proxy/http_query_dispatcher/envoy.yaml").read_text())
    with http_server(app) as special_port, http_server(generic) as generic_port:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            proxy_port = sock.getsockname()[1]
        config["static_resources"]["listeners"][0]["address"]["socket_address"] = {"address": "127.0.0.1", "port_value": proxy_port}
        for cluster in config["static_resources"]["clusters"]:
            address = cluster["load_assignment"]["endpoints"][0]["lb_endpoints"][0]["endpoint"]["address"]["socket_address"]
            address.update(address="127.0.0.1", port_value=special_port if cluster["name"] == "ai_agent_http" else generic_port)
        config_file = tmp_path / "envoy.yaml"
        config_file.write_text(yaml.safe_dump(config))
        with (tmp_path / "envoy.log").open("w") as log:
            process = subprocess.Popen([binary, "-c", str(config_file), "--concurrency", "2", "--log-level", "error"], stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 5
                while True:
                    try:
                        with socket.create_connection(("127.0.0.1", proxy_port), timeout=0.1):
                            break
                    except OSError:
                        assert process.poll() is None, (tmp_path / "envoy.log").read_text()
                        assert time.monotonic() < deadline
                        time.sleep(0.01)
                # Ignore inherited egress proxies only for these loopback requests.
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                def send(path, method="GET", body=None, content_type=None):
                    headers = {"Content-Type": content_type} if content_type else {}
                    req = urllib.request.Request(f"http://127.0.0.1:{proxy_port}{path}", method=method, data=body, headers=headers)
                    try:
                        response = opener.open(req, timeout=35)
                    except urllib.error.HTTPError as error:
                        response = error
                    with response:
                        return response.status, response.read()
                yield send
            finally:
                process.terminate()
                process.wait(timeout=5)


def test_envoy_routes_chat_pages_actions_and_static_assets(routed_http, filesystem_api):
    chat = "/" + filesystem_api[1]["chat"]["Query"]
    for suffix in ("", "/", "?probe=1", "/?probe=1"):
        status, body = routed_http(chat + suffix)
        assert status == 200 and b"Chat history" in body
    status, body = routed_http(chat, "POST", json.dumps({"user_prompt": "Hello\nProxy"}).encode(), "application/json")
    assert status == 200
    assert json.loads(body)["response"] == "Hello\rProxy"
    status, body = routed_http("/ai-agent-ui/static/chat.js")
    assert status == 200 and b'"POST"' in body
    assert routed_http("/ai-agent-ui/healthz")[0] == 200
    assert routed_http(chat, "PUT", b"bad", "application/octet-stream")[0] == 405


def test_envoy_routes_upload_page_and_put(routed_http, filesystem_api):
    upload = "/" + filesystem_api[1]["rag_add"]["Query"]
    status, body = routed_http(upload)
    assert status == 200 and b"Browse file" in body
    status, body = routed_http(upload + "/?ignored=true", "PUT", b"A document\n", "application/octet-stream")
    assert status == 200
    assert json.loads(body)["document"] == "A document\n"


def test_envoy_preserves_generic_paths_methods_queries_and_bodies(routed_http):
    for path in ("/", "/api.pmccabe_collector.restapi.org", "/api.pmccabe_collector.restapi.org/ai_agent/rag/sync/v1", "/api.pmccabe_collector.restapi.org/ai_agent/chat/v1/other", "/static/existing.css"):
        status, body = routed_http(path + "?x=1&y=two", "POST", b"original=body", "application/x-www-form-urlencoded")
        assert status == 200
        assert json.loads(body) == {"backend": "generic", "path": path, "method": "POST", "query": "x=1&y=two", "body": "original=body"}
