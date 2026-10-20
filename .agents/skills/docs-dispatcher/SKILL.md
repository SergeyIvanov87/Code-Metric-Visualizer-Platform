---
name: docs-dispatcher
description: Maintain dispatcher backend compositions, access/store interfaces, and document or chunk storage in ai_agents_framework/docs_dispatcher.
---

Read `ai_agents_framework/docs_dispatcher/sources/backend/dispatcher/README.md`
before changing backend configuration, schemas, or storage behavior.

Treat `mysql_persistent` as a composition, not a renamed MySQL implementation.
Keep the directory layout `backend/{dispatcher,interfaces,mysql_persistent}`,
with `interfaces/{access,store}` for common contracts and utilities, and
`mysql_persistent/{access,store}` for concrete implementations.

Declare the logical fields in the two interface schemas: document path, record
ID, offset, size, parent ID, metadata, and document type. Keep ID and URI mappings
between access and store explicit. `AccessRecordEntryInterface` must expose
semantic record operations and plain records, with no ORM, SQL, engine, or cursor
in its API, so another SQL or NoSQL implementation can fulfill the same contract.

Only the composition binds `MysqlAccessRecordEntry` and
`PersistentStorageRecordEntry`. Shared dispatcher commands must call the selected
interfaces through `dispatcher.runtime.get_backend()`. The MySQL implementation
must not import or reference the storage implementation. Keep all database
queries and engine/credential handling in the access implementation; pass
implementation-specific configuration through opaque runtime options.

Keep shared directory and metadata operations in `StorageRecordEntryInterface`.
Only the persistent store implementation may define `doc_suffix` or access stored
payload files, including chunk placeholders and size queries. Common models
resolve the selected store instead of importing its concrete class. Do not add a
nonpersistent implementation unless requested.

Preserve database-generated directory IDs, filename encoding, metadata formats,
chunk byte ranges, arguments, and JSON/text responses. Keep `current`, Compose
backend defaults, credential file locations, architecture references, and agent
skills consistent with the selected composition. Do not rename MySQL protocol
or external secrets because a composition is named `mysql_persistent`.

Run the existing suite from the repository root:

```sh
PYTHONPATH=ai_agents_framework/docs_dispatcher/sources/backend python -m pytest -q ai_agents_framework/docs_dispatcher/sources/backend/dispatcher/tests
```

Preserve existing test cases and assertions. Adapt import paths, access adapter
arguments, and injected access contexts when changing the architecture; add no
new tests for this task. Report container functional checks separately from local
SQLite/filesystem checks.
