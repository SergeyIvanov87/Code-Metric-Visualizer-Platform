#!/usr/bin/env python3

import json
from pathlib import Path
import time
from urllib.error import URLError
from urllib.request import build_opener, ProxyHandler, Request


GATEWAY = "http://http-api-gateway:8080"
STATE = Path("/gateway-config/merged_routes.json")
opener = build_opener(ProxyHandler({}))


def get_json(path):
    request = Request(GATEWAY + path, headers={"Accept": "application/json"})
    with opener.open(request, timeout=5) as response:
        assert response.status == 200
        return json.load(response)


deadline = time.monotonic() + 60
while True:
    try:
        if STATE.is_file():
            get_json("/first-only")
            break
    except (OSError, URLError):
        pass
    assert time.monotonic() < deadline, "Gateway did not become ready"
    time.sleep(0.25)

state = json.loads(STATE.read_text())
routes = {route["path"]: route for route in state["routes"]}

assert set(routes) == {"/first-only", "/second-only", "/shared"}
assert routes["/first-only"]["cluster"] == "backend_0"
assert routes["/first-only"]["backend"] == "http://provider-first:8080"
assert routes["/second-only"]["cluster"] == "backend_1"
assert routes["/second-only"]["backend"] == "http://provider-second:8080"
assert routes["/shared"]["cluster"] == "backend_1"
assert routes["/shared"]["backend"] == "http://provider-second:8080"

assert get_json("/first-only")["backend"] == "first"
assert get_json("/second-only")["backend"] == "second"
assert get_json("/shared")["backend"] == "second"
assert get_json("/shared/")["backend"] == "second"
assert get_json("/not-advertised")["backend"] == "first"

print("Gateway discovery merge and later-backend precedence verified")
