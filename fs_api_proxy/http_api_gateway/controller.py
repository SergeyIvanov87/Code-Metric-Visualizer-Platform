#!/usr/bin/env python3
"""Discover HTTP API routes and publish Envoy bootstrap and RDS resources."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
from threading import Event
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler


DISCOVERY_PATH = "/.well-known/http-api-routes/v1"
ROUTE_CONFIG_NAME = "http_api_routes"
RDS_TYPE_URL = "type.googleapis.com/envoy.config.route.v3.RouteConfiguration"
MAX_DISCOVERY_BYTES = 1024 * 1024
MAX_ROUTES_PER_BACKEND = 10000
MAX_BACKENDS = 128
MAX_ROUTE_TIMEOUT_SECONDS = 3600
CONFIG_DIRECTORY = Path(os.environ.get("HTTP_API_GATEWAY_CONFIG_DIR", "/var/lib/http-api-gateway"))
BOOTSTRAP_PATH = CONFIG_DIRECTORY / "bootstrap.json"
RDS_PATH = CONFIG_DIRECTORY / "rds.json"
MERGED_ROUTES_PATH = CONFIG_DIRECTORY / "merged_routes.json"
READY_PATH = CONFIG_DIRECTORY / "ready"


class DiscoveryError(ValueError):
    """A backend or discovery document does not satisfy the gateway contract."""


@dataclass(frozen=True)
class Backend:
    index: int
    endpoint: str
    hostname: str
    port: int
    cluster: str

    @property
    def discovery_url(self):
        return self.endpoint.rstrip("/") + DISCOVERY_PATH


def parse_backends(raw_value):
    values = [value.strip() for value in raw_value.split(",") if value.strip()]
    if not values:
        raise DiscoveryError("BACKENDS_FOR_FRONTENDS must contain at least one backend")
    if len(values) > MAX_BACKENDS:
        raise DiscoveryError(f"BACKENDS_FOR_FRONTENDS cannot exceed {MAX_BACKENDS} entries")

    backends = []
    normalized_endpoints = set()
    for index, value in enumerate(values):
        endpoint = value if "://" in value else "http://" + value
        parsed = urlsplit(endpoint)
        if parsed.scheme != "http":
            raise DiscoveryError(f"Backend {value!r} must use http")
        if not parsed.hostname or parsed.username or parsed.password:
            raise DiscoveryError(f"Backend {value!r} has an invalid authority")
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise DiscoveryError(f"Backend {value!r} must not contain a path, query, or fragment")
        try:
            port = parsed.port or 80
        except ValueError as exc:
            raise DiscoveryError(f"Backend {value!r} has an invalid port") from exc
        if not 1 <= port <= 65535:
            raise DiscoveryError(f"Backend {value!r} has an invalid port")
        url_hostname = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        normalized = f"http://{url_hostname}:{port}"
        if normalized in normalized_endpoints:
            raise DiscoveryError("BACKENDS_FOR_FRONTENDS contains duplicate entries")
        normalized_endpoints.add(normalized)
        backends.append(
            Backend(
                index=index,
                endpoint=normalized,
                hostname=parsed.hostname,
                port=port,
                cluster=f"backend_{index}",
            )
        )
    return backends


def normalize_path(path):
    if not isinstance(path, str):
        raise DiscoveryError("Route path must be a string")
    if path == "/" or not path.startswith("/") or path.startswith("//"):
        raise DiscoveryError(f"Route path {path!r} must be a non-root absolute path")
    if any(character in path for character in ("?", "#", "\\", "\x00", "\r", "\n")):
        raise DiscoveryError(f"Route path {path!r} contains a forbidden character")
    if "//" in path or any(segment in (".", "..") for segment in path.split("/")):
        raise DiscoveryError(f"Route path {path!r} is not canonical")
    canonical = path.rstrip("/")
    if canonical == DISCOVERY_PATH:
        raise DiscoveryError("A backend cannot claim the discovery endpoint")
    return canonical


def validate_discovery_document(document, default_timeout_seconds):
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise DiscoveryError("Discovery document must use schema_version 1")
    revision = document.get("revision")
    if not isinstance(revision, str) or not revision:
        raise DiscoveryError("Discovery document revision must be a nonempty string")
    routes = document.get("routes")
    if not isinstance(routes, list):
        raise DiscoveryError("Discovery document routes must be a list")
    if len(routes) > MAX_ROUTES_PER_BACKEND:
        raise DiscoveryError("Discovery document contains too many routes")

    normalized = {}
    for route in routes:
        if not isinstance(route, dict):
            raise DiscoveryError("Every discovery route must be an object")
        path = normalize_path(route.get("path"))
        timeout = route.get("timeout_seconds", default_timeout_seconds)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise DiscoveryError(f"Route {path!r} has an invalid timeout")
        timeout = float(timeout)
        if not 0 < timeout <= MAX_ROUTE_TIMEOUT_SECONDS:
            raise DiscoveryError(f"Route {path!r} has an out-of-range timeout")
        if timeout.is_integer():
            timeout = int(timeout)
        if path in normalized:
            raise DiscoveryError(f"Discovery document contains duplicate route {path!r}")
        normalized[path] = {"path": path, "timeout_seconds": timeout}
    return [normalized[path] for path in sorted(normalized)]


def fetch_backend(backend, timeout_seconds, default_timeout_seconds):
    request = Request(
        backend.discovery_url,
        headers={"Accept": "application/json", "User-Agent": "http-api-gateway/1"},
    )
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get_content_type()
            if response.status != 200:
                raise DiscoveryError(
                    f"{backend.discovery_url} returned HTTP {response.status}"
                )
            if content_type != "application/json":
                raise DiscoveryError(
                    f"{backend.discovery_url} returned {content_type}, expected application/json"
                )
            body = response.read(MAX_DISCOVERY_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise DiscoveryError(f"Cannot query {backend.discovery_url}: {exc}") from exc

    if len(body) > MAX_DISCOVERY_BYTES:
        raise DiscoveryError(f"{backend.discovery_url} response exceeds the size limit")
    try:
        document = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryError(f"{backend.discovery_url} returned invalid JSON") from exc
    return validate_discovery_document(document, default_timeout_seconds)


def merge_routes(backends, snapshots):
    owners = {}
    for backend in backends:
        for route in snapshots[backend.index]:
            owners[route["path"]] = {
                "path": route["path"],
                "timeout_seconds": route["timeout_seconds"],
                "backend": backend.endpoint,
                "cluster": backend.cluster,
            }
    return [owners[path] for path in sorted(owners)]


def duration(seconds):
    return f"{float(seconds):g}s"


def build_bootstrap(backends, listener_port, connect_timeout_seconds, rds_path=RDS_PATH):
    clusters = []
    for backend in backends:
        clusters.append(
            {
                "name": backend.cluster,
                "connect_timeout": duration(connect_timeout_seconds),
                "type": "STRICT_DNS",
                "lb_policy": "ROUND_ROBIN",
                "load_assignment": {
                    "cluster_name": backend.cluster,
                    "endpoints": [
                        {
                            "lb_endpoints": [
                                {
                                    "endpoint": {
                                        "address": {
                                            "socket_address": {
                                                "address": backend.hostname,
                                                "port_value": backend.port,
                                            }
                                        }
                                    }
                                }
                            ]
                        }
                    ],
                },
            }
        )

    return {
        "node": {"cluster": "http_api_gateway", "id": "http_api_gateway"},
        "static_resources": {
            "listeners": [
                {
                    "name": "http_api_gateway",
                    "address": {
                        "socket_address": {
                            "address": "0.0.0.0",
                            "port_value": listener_port,
                        }
                    },
                    "filter_chains": [
                        {
                            "filters": [
                                {
                                    "name": "envoy.filters.network.http_connection_manager",
                                    "typed_config": {
                                        "@type": "type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager",
                                        "stat_prefix": "http_api_gateway",
                                        "normalize_path": True,
                                        "merge_slashes": True,
                                        "path_with_escaped_slashes_action": "REJECT_REQUEST",
                                        "stream_idle_timeout": "0s",
                                        "request_timeout": "0s",
                                        "rds": {
                                            "route_config_name": ROUTE_CONFIG_NAME,
                                            "config_source": {
                                                "resource_api_version": "V3",
                                                "path_config_source": {
                                                    "path": str(rds_path)
                                                },
                                            },
                                        },
                                        "http_filters": [
                                            {
                                                "name": "envoy.filters.http.router",
                                                "typed_config": {
                                                    "@type": "type.googleapis.com/envoy.extensions.filters.http.router.v3.Router"
                                                },
                                            }
                                        ],
                                        "access_log": [
                                            {
                                                "name": "envoy.access_loggers.stdout",
                                                "typed_config": {
                                                    "@type": "type.googleapis.com/envoy.extensions.access_loggers.stream.v3.StdoutAccessLog"
                                                },
                                            }
                                        ],
                                    },
                                }
                            ]
                        }
                    ],
                }
            ],
            "clusters": clusters,
        },
        "admin": {
            "address": {
                "socket_address": {
                    "address": "127.0.0.1",
                    "port_value": 9901,
                }
            }
        },
    }


def build_rds(merged_routes, fallback_backend, fallback_timeout_seconds, revision):
    envoy_routes = []
    for route in merged_routes:
        for path in (route["path"], route["path"] + "/"):
            envoy_routes.append(
                {
                    "match": {"path": path},
                    "route": {
                        "cluster": route["cluster"],
                        "timeout": duration(route["timeout_seconds"]),
                    },
                }
            )
    envoy_routes.append(
        {
            "match": {"prefix": "/"},
            "route": {
                "cluster": fallback_backend.cluster,
                "timeout": duration(fallback_timeout_seconds),
            },
        }
    )
    return {
        "version_info": revision,
        "resources": [
            {
                "@type": RDS_TYPE_URL,
                "name": ROUTE_CONFIG_NAME,
                "virtual_hosts": [
                    {
                        "name": "discovered_http_apis",
                        "domains": ["*"],
                        "routes": envoy_routes,
                    }
                ],
            }
        ],
        "type_url": RDS_TYPE_URL,
    }


def revision_for(merged_routes):
    payload = json.dumps(
        merged_routes, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def atomic_write_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as output:
            json.dump(document, output, sort_keys=True, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def publish_routes(backends, snapshots, fallback_timeout_seconds):
    merged_routes = merge_routes(backends, snapshots)
    revision = revision_for(merged_routes)
    state = {
        "schema_version": 1,
        "revision": revision,
        "routes": merged_routes,
    }
    atomic_write_json(
        RDS_PATH,
        build_rds(merged_routes, backends[0], fallback_timeout_seconds, revision),
    )
    atomic_write_json(MERGED_ROUTES_PATH, state)
    atomic_write_json(READY_PATH, {"revision": revision})
    return revision


def poll_backends(backends, snapshots, timeout_seconds, default_timeout_seconds):
    changed = False
    failures = []
    with ThreadPoolExecutor(max_workers=len(backends)) as executor:
        pending = {
            executor.submit(
                fetch_backend, backend, timeout_seconds, default_timeout_seconds
            ): backend
            for backend in backends
        }
        for future in as_completed(pending):
            backend = pending[future]
            try:
                routes = future.result()
            except DiscoveryError as exc:
                failures.append((backend, exc))
                continue
            if snapshots.get(backend.index) != routes:
                snapshots[backend.index] = routes
                changed = True
    return changed, failures


def positive_number(name, default):
    raw = os.environ.get(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise DiscoveryError(f"{name} must be numeric") from exc
    if value <= 0:
        raise DiscoveryError(f"{name} must be positive")
    return value


def positive_integer(name, default):
    value = positive_number(name, default)
    if not value.is_integer():
        raise DiscoveryError(f"{name} must be an integer")
    return int(value)


def run():
    backends = parse_backends(os.environ.get("BACKENDS_FOR_FRONTENDS", ""))
    listener_port = positive_integer("HTTP_API_GATEWAY_LISTEN_PORT", 8080)
    if listener_port > 65535:
        raise DiscoveryError("HTTP_API_GATEWAY_LISTEN_PORT must not exceed 65535")
    poll_interval = positive_number("HTTP_API_DISCOVERY_POLL_INTERVAL_SECONDS", 15)
    request_timeout = positive_number("HTTP_API_DISCOVERY_TIMEOUT_SECONDS", 5)
    default_route_timeout = positive_number("HTTP_API_DEFAULT_ROUTE_TIMEOUT_SECONDS", 60)
    fallback_timeout = positive_number("HTTP_API_FALLBACK_TIMEOUT_SECONDS", 60)
    connect_timeout = positive_number("HTTP_API_CONNECT_TIMEOUT_SECONDS", 5)

    CONFIG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    READY_PATH.unlink(missing_ok=True)
    atomic_write_json(
        BOOTSTRAP_PATH,
        build_bootstrap(backends, listener_port, connect_timeout),
    )

    stop = Event()

    def request_stop(_signum, _frame):
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    snapshots = {}
    published_revision = None
    while not stop.is_set():
        changed, failures = poll_backends(
            backends, snapshots, request_timeout, default_route_timeout
        )
        for backend, error in failures:
            print(
                f"Discovery failed for backend {backend.endpoint}: {error}",
                file=sys.stderr,
                flush=True,
            )

        if len(snapshots) == len(backends):
            merged = merge_routes(backends, snapshots)
            revision = revision_for(merged)
            if changed or revision != published_revision:
                published_revision = publish_routes(
                    backends, snapshots, fallback_timeout
                )
                print(
                    f"Published {len(merged)} routes at {published_revision}",
                    flush=True,
                )
        else:
            missing = [
                backend.endpoint
                for backend in backends
                if backend.index not in snapshots
            ]
            print(
                "Waiting for initial discovery from: " + ", ".join(missing),
                file=sys.stderr,
                flush=True,
            )

        stop.wait(poll_interval)


def main():
    try:
        run()
    except DiscoveryError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
