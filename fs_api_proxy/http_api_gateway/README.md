# HTTP API gateway

The HTTP API gateway routes requests to an ordered list of backend-for-frontend
HTTP services. Each backend publishes the exact paths it owns through:

```text
GET /.well-known/http-api-routes/v1
```

The controller polls all configured backends, keeps each backend's last valid
snapshot, and merges routes from left to right. A later backend replaces an
earlier backend when both advertise the same path. The first backend remains
the catch-all for paths that are not advertised.

## Discovery contract

A backend responds with `application/json`:

```json
{
  "schema_version": 1,
  "revision": "sha256:...",
  "routes": [
    {
      "path": "/api.pmccabe_collector.restapi.org/example/v1",
      "timeout_seconds": 60
    }
  ]
}
```

Paths are owned for all HTTP methods. The gateway emits exact matches for the
canonical path and its trailing-slash form. Root, prefix, noncanonical, and
discovery-endpoint claims are rejected.

## Configuration

`BACKENDS_FOR_FRONTENDS` is required runtime configuration. Entries may omit
the `http://` scheme but must include a port when the service does not listen
on port 80:

```sh
BACKENDS_FOR_FRONTENDS=http://rest-api:5000,http://ai-agent-http-ambassador:8081
```

The setting belongs in the deployment environment, not a Docker build argument.
Changing the list requires recreating both gateway services because the list
also defines the Envoy clusters.

Other settings:

| Variable | Default | Purpose |
| --- | ---: | --- |
| `HTTP_API_GATEWAY_PORT` | `8080` | Published gateway port |
| `HTTP_API_DISCOVERY_POLL_INTERVAL_SECONDS` | `15` | Polling interval |
| `HTTP_API_DISCOVERY_TIMEOUT_SECONDS` | `5` | Per-backend request timeout |
| `HTTP_API_DEFAULT_ROUTE_TIMEOUT_SECONDS` | `60` | Missing route timeout |
| `HTTP_API_FALLBACK_TIMEOUT_SECONDS` | `60` | Catch-all timeout |
| `HTTP_API_CONNECT_TIMEOUT_SECONDS` | `5` | Envoy upstream connect timeout |

## Runtime configuration

The controller writes three atomic runtime artifacts to the shared configuration
volume:

- `bootstrap.json`: listener and fixed backend clusters.
- `rds.json`: filesystem xDS route discovery response.
- `merged_routes.json`: normalized diagnostic ownership list.

Envoy starts after initial discovery succeeds for every configured backend. A
poll failure retains the last valid snapshot; only a valid response can remove
or replace routes. The RDS file is replaced atomically so Envoy can apply route
updates without restarting or interrupting active requests.

## Run

All backends and gateway services must share
`api.pmccabe_collector.network`.

```sh
BACKENDS_FOR_FRONTENDS=http://rest-api:5000,http://ai-agent-http-ambassador:8081 \
  docker compose -f fs_api_proxy/http_api_gateway/compose.yaml up --build
```

## Functional test

The isolated test stack starts two stub providers. Both claim one common path;
the second provider must own that path after merging.

```sh
docker compose \
  -f fs_api_proxy/http_api_gateway/tests/functional/compose-functional.test.yaml \
  up --build --abort-on-container-exit \
  --exit-code-from http-api-gateway-functional-tester
```
