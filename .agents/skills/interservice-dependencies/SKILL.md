---
name: interservice-dependencies
description: Use when declaring consumed filesystem APIs in API/deps, adding all_dependencies or unmet_dependencies endpoints, gating service startup or functional/integration tests on API readiness, or diagnosing missing-FIFO startup races.
---

# Manage interservice dependencies

A service depends on another service when it uses that service's API. Trace the
consumer's calls before declaring dependencies; Compose startup order alone does
not establish filesystem API readiness. Use
[filesystem API development](../filesystem-api-development/SKILL.md) for schema,
generator, FIFO and session contracts, and
[container test diagnostics](../container-test-diagnostics/SKILL.md) for test
selection, Compose wiring and evidence collection.

## Inspect the working pattern

Read [service broker startup](../../../service_broker/init.sh),
[its dependency schemas](../../../service_broker/API/deps), and
[its functional tester](../../../service_broker/tests/functional/init.sh).
Check the current shared implementation before adapting it:

- [init helpers](../../../common/shell_utils/init_utils.sh):
  `launch_command_api_services`, `wait_for_unavailable_services`, and
  `gracefull_shutdown`.
- [command generation](../../../common/build_common_api_services.py) and
  [canonicalization](../../../common/canonize_internal_api.py).
- [dependency discovery](../../../common/modules/api_deps_utils.py),
  [static listing](../../../common/get_service_api_deps.py), and
  [availability checks](../../../common/check_missing_pseudo_fs_from_schema.py).

`all_dependencies` lists static declared dependencies. `unmet_dependencies`
checks discovery and FIFO validity and sends keep-alive probes to found APIs;
an empty response means no unmet dependencies. A directory or container existing
is insufficient. These checks do not prove successful application processing.

## Declare consumed APIs

1. Trace the consumer's wrappers, generators and processors to the providers'
   authoritative `API/*.json`. Include every external filesystem endpoint used,
   preserving `Query`, `Method`, `Content-Type`, `Params` and version.
   Distinguish internal calls to the service's own API from external dependencies.
2. Create `<consumer>/API/deps/<provider-name>/*.json` with copies of the consumed
   provider schemas. Use a direct child directory for each provider, as the current
   discovery code expects. Use `API/deps`, not `AP/deps`.
3. Keep provider queries addressed to the provider. Canonicalize relative queries
   against the correct owning service; do not rewrite them to the consumer.
   Keep copies aligned when the provider contract changes.
4. Put the consumer's `all_dependencies.json` and `unmet_dependencies.json`
   directly in `API/deps`, following the broker's command schemas. These describe
   the consumer's management endpoints, not a downstream provider.
5. Inspect Dockerfile copies, generated working directories, development mounts,
   Compose environment and the shared API volume. Ensure the schemas and common
   utilities are available in the actual runtime image.

For an AI-agent change, start at
[agent sources](../../../ai_agents_framework/ai_agent/sources),
[dispatcher schemas](../../../ai_agents_framework/docs_dispatcher/API), and
[uploader schemas](../../../utility/file-uploader/API). Use direct dependency
directories such as `API/deps/docs_dispatcher` and `API/deps/file-uploader`,
rather than nesting repository paths under `deps`. Trace all RAG processors and
`fs_api_wrappers.py`: bulk-add currently consumes `streaming_directory_events`.
Verify whether `streaming_file_upload` or additional uploader endpoints are
actually consumed before adding them; an example filename is not usage evidence.
Track non-filesystem dependencies, such as a vector-store connection, through
their own readiness mechanism.

## Gate service readiness

1. Export `DEPEND_ON_SERVICES_API_SCHEMA_DIR` to the runtime `API/deps`.
   Initialize PID tracking and shutdown handling before starting child processes.
2. Call `launch_command_api_services` with the tracked PID array, dependency
   schema directory, writable work directory, shared API directory and
   `"${MAIN_SERVICE_NAME}/${MICROSERVICE_NAME}"`. It canonicalizes command
   schemas, builds their executors and FIFOs, and launches the command servers.
   Use the established privilege variant if permissions require it.
3. Include both owned command and business API schemas in API-manager cleanup.
   Trace generated paths and managers; do not make the consumer remove its
   providers' pipes. Register command servers in shutdown tracking too.
4. Print the `SKIP_API_DEPS_CHECK` setting. Following broker semantics, when it
   equals `false`, run the following before declaring the service operable:

   ```bash
   if [ "${SKIP_API_DEPS_CHECK:-}" = false ]; then
       if wait_for_unavailable_services "${SHARED_API_DIR}" \
           "${MAIN_SERVICE_NAME}/${MICROSERVICE_NAME}" \
           "${TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC}"; then
           :
       else
           echo -e "${BRed}ERROR: As required APIs are missing, the service considered as inoperable. Abort${Color_Off}"
           gracefull_shutdown SERVICE_WATCH_PIDS "${API_MANAGEMENT_PID}"
           exit 255
       fi
   fi
   ```

   Verify the variable's default and propagation in each deployment/test model.
   The current helper's third argument is a retry count despite the caller's
   `...SEC` name; its initial command-FIFO and response-appearance waits can be
   unbounded. Do not describe it as an overall seconds deadline. Use an outer
   test deadline when validating missing-service behavior.
5. Ensure the service's own API servers and FIFOs are initialized too. Only after
   its startup work and dependency gate succeed, print
   `echo -e "${BGreen}The service is ready${Color_Off}"`.
   Check EXIT/signal traps so failure remains nonzero and cleanup does not turn
   `exit 255` into success. Adapt PID/manager arguments to the actual service.

## Gate functional and integration tests

Before any API-conformance or business tests, call
`wait_for_unavailable_services "${SHARED_API_DIR}" "${MAIN_SERVICE_NAME}/<service-under-test>"`.
On nonzero status, report failure, clean up tester-owned processes and exit 255.
Use the service under test's command endpoint, not a tester-owned replacement.
A tester with no child processes need not invent a PID array or API manager.

In isolated tests, prepare working mock providers for the declared APIs before
waiting, following the broker functional tester. Do not mock the tested service's
own management endpoints. In integration tests, wait on the real service.
Inspect every functional/integration entrypoint and inherited Compose model;
do not add the wait only to one test path. For the AI agent, inspect
[test startup](../../../ai_agents_framework/ai_agent/test/init.sh) and how the
common tests are copied into its image.

An empty dependency report does not by itself prove the service's own API
initialization has finished. Verify required owned FIFOs/listeners are ready
before the tester proceeds; add an appropriate readiness barrier if needed.
A missing `exec` or `result.json` during startup is evidence to compare against
provider initialization times, rather than a reason to add a fixed sleep.

## Verify and report

For an implementation change, validate JSON and shell syntax, then resolve the
chosen Compose model with `docker compose -f <selected-file> config --quiet`.
Run the smallest owning functional scope and relevant integration scope using
[container test diagnostics](../container-test-diagnostics/SKILL.md).

Verify observable behavior: static listing matches consumed endpoints; delayed
providers hold startup/tests; missing or unresponsive APIs appear in the unmet
report; restoration clears it; failure exits nonzero; and ready is printed only
after successful initialization. Check that tests do not race the service's own
FIFO creation and that shutdown preserves provider-owned resources.

For outage tests use
[UnavailableAPI](../../../common/tests/unavailable_api.py), which masks the request
FIFO while preserving live result FIFOs. See
[its regression checks](../../../common/test_unavailable_api.py); run
`python -m pytest -q common/test_unavailable_api.py` when changing that mechanism.
Do not move live result FIFOs to simulate an outage.

For a skill-only change, check frontmatter, relative links, discoverability and
examples against current source; runtime suites are not required.
Report declared providers/endpoints, readiness ordering, exact checks run and
remaining limitations. Distinguish a documented procedure from a runtime fix.
