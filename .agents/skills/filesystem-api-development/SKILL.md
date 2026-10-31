---
name: filesystem-api-development
description: Use when adding or changing API JSON schemas, generated shell executors, FIFO request handling, session isolation, REST exposure, or deferred query lifecycle.
---

# Change filesystem APIs

Read the [API source map](../../../HowTo/Agent-Repository-Map.md#filesystem-api-contract) and the nearest existing schema before implementing.

1. Locate the owning `API/*.json`. Preserve `Query`, `Method`, `Content-Type`, nested `Params`, and their relationship to the service generator. Consult `common/modules/api_schema_utils.py` for actual parsing rules.
2. Update the schema and generator or processor together. Follow `common/modules/api_fs_conventions.py` for paths and `common/modules/api_fs_args.py` for argument handling. Do not edit only a generated `services/*_exec.sh`.
3. Preserve both CLI FIFOs and GUI access/modify listeners where applicable. `GET`, `PUT`, and `POST` are filesystem protocol operations as well as HTTP methods.
4. Write newline-terminated requests to `exec`. Use existing query helpers rather than inventing framing. Match `SESSION_ID` with the corresponding `result.<extension>_<SESSION_ID>` response; use the content type to determine the extension.
5. For deferred work, trace `common/deferred_query_launcher.py` and `common/deferred_query_executor.py`. Keep the initial handshake distinct from final asynchronous completion. Respect initial-query, update, and result-consumption timeout semantics. Validate arguments before accepting work, retain processor errors, and keep payloads larger than `PIPE_BUF` intact.
6. Follow [interservice dependencies](../interservice-dependencies/SKILL.md) when declaring consumed APIs or changing dependency command endpoints and startup/test readiness gates. Trace affected `API/deps` consumers and the REST adapter in `rest_api/rest_api_server/rest_api_server`. Preserve response content type and error reporting through both transports.
7. Add focused behavior coverage for the changed contract: session isolation, invalid arguments, disconnected readers, timeout, shutdown, or large payloads as relevant. Run the owning functional tests and common lifecycle tests when generation/transport changes.

## Ownership and permissions

Containers create, serve, and remove their filesystem APIs as their own service
users. Service and tester users must remain distinct. Never use superuser
privileges, `doas`, `sudo`, or runtime `chown` to create API artifacts or bypass
ownership. Restore any required image setup at build time; an installed elevation
tool does not authorize using it after container startup.

The image initializes `/api` with mode `0777`. Keep these runtime permissions,
as implemented by `common/build_api_pseudo_fs.py` and the shared server generator:

| Node | Required permissions |
| --- | --- |
| Request directory containing `0.<parameter>`, `1.<parameter>`, etc. | Add `stat.S_IWUSR \| stat.S_IRUSR \| stat.S_IWGRP \| stat.S_IRGRP \| stat.S_IWOTH \| stat.S_IROTH` (`0666` read/write mask), preserving existing directory traversal bits. |
| Terminal method directory, such as `GET`, `PUT`, or `POST` | `stat.S_IRUSR \| stat.S_IXUSR \| stat.S_IWUSR \| stat.S_IRGRP \| stat.S_IXGRP \| stat.S_IROTH \| stat.S_IXOTH` (`0755`). |
| `exec` FIFO | `0622`. |
| `result*` FIFO, including session results | `0644`. |

Clients write requests to `exec` and read `result*`. They do not need ownership
or permission to rename, replace, or delete provider-owned nodes. Do not widen
directory permissions, share service/tester UIDs, or elevate tests to simulate
an outage. Use tester-owned fixtures for mutation-based outage checks; check
live availability through the provider's public API in integration tests.

## Checks

From the repository root, the focused deferred transport checks are:

```sh
python -m pytest -q common/test_deferred_query_executor.py
```

The container suite covers service creation, API queries, multiple sessions, and graceful shutdown; see [test diagnostics](../container-test-diagnostics/SKILL.md). After stopping a test service, check that request FIFOs and results were removed, including deferred request resources. Persistent shared staging has a different lifetime: see [streaming ingestion](../streaming-ingestion/SKILL.md).

## Architecture references

Read these when changing deferred ownership, handshakes, timeouts, or shutdown:

- [Async file API implementation recap](../../../Architecture_Design_Decisions/Async-File-API-Design%23115/implementation_v1.md): explains why the launcher exits after readiness, the processor chooses its input channel, and the executor owns bounded result delivery and cleanup. Its “Differences from `Review.md`” section distinguishes the implementation from the original design.
- [Original async API review](../../../Architecture_Design_Decisions/Async-File-API-Design%23115/Review.md): useful for lifecycle rationale, failure cases, and acceptance scenarios. Its plain-path handshake and executor-owned input model are historical proposals, not the current JSON handshake and processor-owned channel contract.

The recap is also a versioned snapshot; verify current integrity options, timeout behavior, and limits in the uploader schema and deferred utilities rather than adopting its known-gap list unchanged.

## Completion

Describe the schema and runtime changes, affected consumers, and actual checks run. Do not treat successful handshake publication as processor success.
