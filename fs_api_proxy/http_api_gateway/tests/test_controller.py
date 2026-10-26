import sys
from pathlib import Path

import pytest

SERVICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE))

from controller import (
    Backend,
    DiscoveryError,
    build_rds,
    merge_routes,
    nonnegative_number,
    parse_backends,
    revision_for,
    validate_discovery_document,
)


def backend(index, endpoint):
    return Backend(
        index=index,
        endpoint=endpoint,
        hostname="provider",
        port=8080,
        cluster=f"backend_{index}",
    )


def test_later_backend_owns_duplicate_path():
    backends = [backend(0, "http://first:8080"), backend(1, "http://second:8080")]
    snapshots = {
        0: [
            {"path": "/first-only", "timeout_seconds": 60},
            {"path": "/shared", "timeout_seconds": 60},
        ],
        1: [
            {"path": "/second-only", "timeout_seconds": 30},
            {"path": "/shared", "timeout_seconds": 30},
        ],
    }

    routes = {route["path"]: route for route in merge_routes(backends, snapshots)}

    assert routes["/first-only"]["cluster"] == "backend_0"
    assert routes["/second-only"]["cluster"] == "backend_1"
    assert routes["/shared"]["cluster"] == "backend_1"
    assert routes["/shared"]["backend"] == "http://second:8080"

    merged = list(routes.values())
    discovery_response = build_rds(merged, backends[0], 60, revision_for(merged))
    envoy_routes = discovery_response["resources"][0]["virtual_hosts"][0]["routes"]
    shared = next(route for route in envoy_routes if route["match"] == {"path": "/shared"})
    assert shared["route"]["cluster"] == "backend_1"
    assert envoy_routes[-1]["match"] == {"prefix": "/"}
    assert envoy_routes[-1]["route"]["cluster"] == "backend_0"


def test_zero_fallback_timeout_disables_envoy_cap():
    first = backend(0, "http://first:8080")
    response = build_rds([], first, 0, revision_for([]))
    fallback = response["resources"][0]["virtual_hosts"][0]["routes"][-1]
    assert fallback["route"]["timeout"] == "0s"


def test_fallback_timeout_accepts_zero_but_rejects_negative(monkeypatch):
    monkeypatch.setenv("TIMEOUT", "0")
    assert nonnegative_number("TIMEOUT", 60) == 0
    monkeypatch.setenv("TIMEOUT", "-1")
    with pytest.raises(DiscoveryError, match="must not be negative"):
        nonnegative_number("TIMEOUT", 60)


def test_backend_endpoints_are_normalized_before_duplicate_detection():
    backends = parse_backends("first,http://second:8080")
    assert [backend.endpoint for backend in backends] == [
        "http://first:80",
        "http://second:8080",
    ]

    with pytest.raises(DiscoveryError, match="duplicate"):
        parse_backends("first,http://first:80")


@pytest.mark.parametrize(
    "path",
    ["/", "relative", "//double", "/a//b", "/a/../b", "/path?query=1", "/.well-known/http-api-routes/v1"],
)
def test_discovery_rejects_unsafe_or_reserved_paths(path):
    with pytest.raises(DiscoveryError):
        validate_discovery_document(
            {
                "schema_version": 1,
                "revision": "test",
                "routes": [{"path": path, "timeout_seconds": 60}],
            },
            60,
        )
