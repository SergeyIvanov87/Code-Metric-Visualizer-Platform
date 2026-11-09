---
name: docs-dispatcher
description: Maintain dispatcher backend aggregators, access/store contracts, and reusable document implementations in ai_agents_framework/docs_dispatcher.
---

Read `ai_agents_framework/docs_dispatcher/sources/backend/dispatcher/README.md`
before changing configuration, schemas, or document behavior.

Keep `BackendConfig` data-only. `BackendDispatcher()` loads it inside its
no-argument constructor; top-level `sources/*.py` scripts must not import, load,
or access configuration. They obtain opened access and store instances with
`with BackendDispatcher().get_backend() as backend` and call their interfaces.
Keep scripts limited to arguments, input, output, and exit-status handling.

Keep each access and store contract in `interfaces/{access,store}/interface.py`,
re-export it from the package `__init__.py`, and keep shared record schemas under
`interfaces/schema`.
Keep the abstract backend contract in `interfaces/backend/interface.py`. A
composition package such as `mysql_persistent` implements `Backend.create_instance()`
and owns creation and cleanup of its access and store instances. Dispatcher runtime
selects that concrete class and delegates to its factory; it must not instantiate
access or store interfaces itself.

Reusable concrete implementations belong in `interfaces_impl/access/mysql` and
`interfaces_impl/store/persistent`, as peers of `interfaces`. Do not introduce backend
command modules, concrete imports in scripts, a storage operations module, or a
separate CRUD forwarding module. Implement application operations in the two
concrete interface classes. Keep only required operations in the contracts;
implementation-specific utilities must not constrain future SQL or NoSQL access.

`RuntimeConfig` contains only `options` and `spec_path`. All implementation
settings, including `storage_uri`, are opaque options to the dispatcher. Each
implementation validates its own options. Do not require filesystem locations or
SQL credentials in generic runtime configuration.

Preserve the logical schema: document path, ID, offset, size, parent ID, metadata,
and document type. Return plain access/storage records rather than ORM objects.
Cross-store operations receive the other interface explicitly; MySQL access may
not import a concrete store, and persistent storage may not import MySQL access.
Only persistent storage defines `doc_suffix` or performs payload IO. Keep shared
directory/metadata utilities in the store contract. Storage models are data-only
and must not select a backend or perform filesystem work.

Preserve database-generated IDs, URI encoding, metadata formats, byte ranges,
rollback behavior, arguments, JSON/text responses, and exit statuses. Keep
Compose credential paths, documentation, CI registration, and other skills
consistent with moves. Do not rename MySQL protocol names or external secrets.
Do not add a nonpersistent backend unless requested.

The existing 20 backend cases belong to `tests/unit/cases` and are registered by
`tests/unit/Dockerfile` and `init.sh`. Preserve their scenarios and expected
results; adapt calls to the new interfaces, and add no test cases for this task.
Never invoke a test runner directly. Run the owning container:

```sh
docker compose -f ai_agents_framework/docs_dispatcher/compose-unit.test.yaml up --build --abort-on-container-exit --exit-code-from docs-dispatcher-unit-tester
```

Run the existing dispatcher functional stack for public API changes, following
[container test diagnostics](../container-test-diagnostics/SKILL.md). Distinguish
SQLite/contract checks from public API checks and live MySQL checks in reports.
