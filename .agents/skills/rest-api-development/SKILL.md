---
name: rest-api-development
description: Use when changing filesystem API discovery, generated REST pages, query forms, or the REST service functional tests.
---

# Develop the REST API browser

Read `rest_api/build_api_cgi.py`, `rest_api/api_browser_utils.py`, the templates,
and the existing functional tester before editing. Use `service_name`,
`service_page_url`, and `request_fields` for shared metadata and URL conventions.
A query directly below the API domain has no service name and stays ungrouped
on the landing page. Group only paths containing a service and an operation.
Preserve the existing fixture queries; add separate schemas and executor
registrations when new coverage is needed.

The REST browser groups recovered schemas by the first component after the API
domain. Its generated pages and method templates are owned by
`rest_api/build_api_cgi.py` and `rest_api/rest_api_server/rest_api_server/templates`.
Keep navigation separate from direct API execution and include inherited
filesystem parameters. Place REST tests in
`rest_api/tests/functional/service_tester/` and use the predefined schemas under
`rest_api/tests/functional/data/`. Check the existing `http://rest-api:5000`
instance for container links, API links, editable parameters, and execution;
do not construct another Flask application or test client.

All executable tests must belong to a testing container and run only through
its Dockerfile and `init.sh`; do not create or run standalone tests in
`rest_api/tests/` or invoke a test runner directly. Use
[container test diagnostics](../container-test-diagnostics/SKILL.md) for the
temporary virtual environment and Dockerfile layout required for agent-local
reproduction. The REST container entrypoint runs the registered checks:

```sh
docker compose -f rest_api/compose-functional.test.yaml config --quiet
docker compose -f rest_api/compose-functional.test.yaml up --build --abort-on-container-exit --exit-code-from rest-api-functional-service-tester
```

Use the generic [container test diagnostics](../container-test-diagnostics/SKILL.md)
for environment setup and authoritative tester status. Do not add REST-specific
execution details to generic filesystem or container skills.

For TLS-inspecting proxies, set `PROXY_CA_FILE` to an absolute path to a readable
PEM CA file before the normal Compose build/up commands. With no value or an
empty file, the stack uses system trust. Dockerfiles use the shared wrapper under
`common/proxy_setup_image_helpers/` with optional BuildKit secrets; no extra CA
is persisted. Compose entrypoints import that directory's `compose-proxy-trust.yaml`
resource. The REST runtime entrypoint uses the same wrapper; `test_proxy_ca.py` checks missing, empty, and supplied files via
the existing tester entrypoint. Keep this configuration independent of any
specific development environment.
