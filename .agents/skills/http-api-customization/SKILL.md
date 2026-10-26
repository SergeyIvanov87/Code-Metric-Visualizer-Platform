---
name: http-api-customization
description: Use when changing the pseudo-BFF HTTP API gateway, discovery contract, route precedence, BACKENDS_FOR_FRONTENDS integration, or creating an HTTP ambassador/embassador provider that adapts frontend requests to filesystem APIs or internal services.
---

# Customize discovered HTTP APIs

Read the current [gateway controller](../../../fs_api_proxy/http_api_gateway/controller.py),
[gateway README](../../../fs_api_proxy/http_api_gateway/README.md), and the closest
provider before editing. Treat current code and tests as authoritative when this
skill drifts.

## Understand the pseudo-BFF model

Use “pseudo-BFF” as repository terminology, not as a claim that the complete
system implements the conventional Backend for Frontend pattern:

- Envoy is a generic API gateway.
- The controller pulls route documents from ordered HTTP route providers.
- An ambassador may be BFF-like when it adapts a frontend-specific HTTP
  experience to a filesystem API or another internal protocol.
- A provider owns behavior and route declarations; the gateway owns validation,
  precedence, clusters, and forwarding.

Preserve these routing rules:

1. Poll every provider at `GET /.well-known/http-api-routes/v1`.
2. Merge providers from left to right. A later provider replaces an earlier
   provider for the same normalized path.
3. Route unadvertised paths to the first provider as the catch-all.
4. Match each advertised path exactly and also accept its trailing-slash form.
5. Route all HTTP methods for a path to one provider. Discovery v1 cannot assign
   different methods on the same path to different providers.
6. Require one valid initial document from every provider before declaring the
   controller ready. After that, retain each provider's last valid snapshot
   across polling failures.
7. Generate private cluster names such as `backend_0`; never add
   service-specific cluster names or route regexes to a static Envoy file.

The controller writes `bootstrap.json`, `rds.json`,
`merged_routes.json`, and `ready` under
`/var/lib/http-api-gateway`. It replaces RDS atomically, so route changes do
not restart Envoy. Provider topology remains part of the bootstrap: changing
`BACKENDS_FOR_FRONTENDS` requires recreating the controller and gateway.

## Preserve the discovery contract

Return `application/json` with this shape:

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

Build the document from the provider's source of truth, normally its
`API/*.json` schemas. Do not copy route strings into both the handler and the
discovery response.

- Sort normalized routes by path.
- Compute a deterministic revision from canonical JSON of the sorted routes.
- Start every route with `/` and reject root, queries, fragments, repeated
  slashes, backslashes, dot segments, control characters, and the discovery
  endpoint itself.
- Keep paths unique within one provider.
- Use a positive timeout no greater than 3600 seconds. Make it long enough for
  the provider to return its own timeout response; the existing ambassador adds
  ten seconds to its filesystem operation deadline.
- Omit `timeout_seconds` only when the gateway's configured default is suitable
  for that action.
- Advertise an action path once even when GET renders its page and POST or PUT
  performs the action.
- Do not advertise `/healthz` or private asset paths unless external clients
  are intentionally meant to reach them through the gateway.

The current controller requires a nonempty `revision`, but republishes routing
only when normalized route ownership changes. Do not use revision-only changes
as a signaling mechanism.

Use these producers as examples:

- [REST discovery generation](../../../rest_api/build_api_cgi.py)
- [AI agent ambassador](../../../ai_agents_framework/ai_agent_http_embassador/server.py)

## Create an HTTP ambassador

1. **Choose the boundary.** Identify the frontend actions and the owning
   downstream API. Use an ambassador only when HTTP presentation, validation,
   aggregation, or protocol adaptation is needed. A service that merely owns an
   HTTP endpoint can be a route provider without an ambassador.
2. **Inspect the source contract.** Read the owning schemas and implementation.
   Preserve methods, content types, parameters, timeouts, error semantics, and
   session behavior. When adapting filesystem APIs, also use
   [filesystem-api-development](../filesystem-api-development/SKILL.md). Use
   [agentic-rag-development](../agentic-rag-development/SKILL.md) if document,
   retrieval, or inference behavior changes.
3. **Create a self-contained service.** Prefer a correctly spelled
   `<owner>_http_ambassador` for new directories; retain the existing
   `ai_agent_http_embassador` spelling for compatibility. Add the server,
   templates/static sources when needed, runtime configuration, requirements,
   Dockerfile, Compose fragment, and focused tests.
4. **Derive public paths.** Load route paths from the owning schemas or another
   single source of truth. Validate supported schema methods and content types
   during application startup.
5. **Adapt requests safely.** Validate JSON fields, media types, Unicode, and
   size limits before calling downstream code. Reuse the existing FIFO client
   and session framing for filesystem APIs. Never pass caller-controlled paths
   or metadata into shell-based executors without the owning subsystem's
   validation rules.
6. **Handle long operations honestly.** Map unavailable dependencies, invalid
   downstream results, and timeouts to distinct HTTP statuses. Do not retry an
   operation when completion is unknown. Preserve staged input when a timed-out
   downstream operation may still consume it; otherwise clean it up.
7. **Keep UI implementation private.** Avoid public service-specific prefixes
   such as `/ai-agent-ui`. Inline small trusted assets with CSP nonces or serve
   them only when they are deliberately part of the public contract. Place
   inline scripts after their DOM controls or wait for `DOMContentLoaded`;
   `defer` does not delay classic inline scripts.
8. **Publish discovery.** Generate the versioned document at the standard
   endpoint and keep `/healthz` separate. Return JSON for HTTP errors and
   apply security/cache headers consistently.
9. **Package for the shared network.** Expose the ambassador port to
   `api.pmccabe_collector.network` without publishing it to the host unless
   direct access is required. Use repository-root Docker build contexts when
   the image copies files across service directories. Mount only required
   configuration and shared data.
10. **Insert it at the intended precedence.** Add its internal URL to
    `BACKENDS_FOR_FRONTENDS` in the root Compose model. Put a generic provider
    first and specialized ambassadors later when they must replace generic
    routes. Do not customize Envoy configuration for the new service.

The existing integration is in
[compose.rag-agent.http.streaming.yaml](../../../ai_agents_framework/compose.rag-agent.http.streaming.yaml).

## Test the change

Start with the smallest owning checks, then cover the routing boundary:

```sh
python3 -m pytest -q fs_api_proxy/http_api_gateway/tests/test_controller.py
python3 -m pytest -q rest_api/tests/test_build_api_cgi.py
python3 -m pytest -q ai_agents_framework/ai_agent_http_embassador/tests
```

For a new ambassador, add tests that prove:

- its discovery response is deterministic and contains exactly its public
  action paths;
- GET pages and action methods work at the same discovered paths;
- validation, downstream errors, timeouts, and cleanup remain correct;
- embedded browser scripts attach after their DOM controls;
- private health and asset paths are not advertised.

Extend the isolated gateway functional stack when changing discovery or
precedence. Keep two stub providers with an overlapping route and prove that
the second provider owns both the merged entry and the forwarded request:

```sh
docker compose \
  -f fs_api_proxy/http_api_gateway/tests/functional/compose-functional.test.yaml \
  config --quiet
docker compose \
  -f fs_api_proxy/http_api_gateway/tests/functional/compose-functional.test.yaml \
  up --build --abort-on-container-exit \
  --exit-code-from http-api-gateway-functional-tester
```

Use [container-test-diagnostics](../container-test-diagnostics/SKILL.md) when
selecting or diagnosing Compose checks. Inspect resolved build contexts,
external networks/volumes, readiness, tester status, and logs before teardown.

## Completion

Report the provider order, advertised paths, collisions and their winners,
fallback behavior, affected consumers, checks run, and anything not exercised
with a real Envoy/container stack. State explicitly when a topology change
requires recreation rather than a dynamic RDS update.
