---
name: docs-dispatcher
description: Maintain dispatcher backends, backend selection, and document or chunk filesystem storage in ai_agents_framework/docs_dispatcher.
---

Read `ai_agents_framework/docs_dispatcher/sources/backend/dispatcher/README.md`
before changing backend configuration or storage behavior.

Use `mysql_persistent` for the persistent backend name, Python package, and YAML
specification. Keep `current`, Compose defaults, module imports, secret file
paths, and architecture documentation consistent when renaming a backend.
Do not rename the MySQL protocol, database settings, or external secret names
merely because the backend implementation name changes.

Keep record directory and metadata operations in `StorageRecordEntryInterface`.
Only `PersistentStorageRecordEntry` may define `doc_suffix` or access stored
payload files, including chunk placeholders and payload size queries. Delegate
from `StorageRecord` and command modules instead of calling filesystem APIs on
payload paths. The shared interface must remain usable without stored document
content; do not add a nonpersistent implementation unless requested.

Preserve database-generated directory IDs, filename encoding, metadata formats,
chunk byte ranges, command arguments, and JSON responses. Keep backend routing
and backend configuration loading consistent for both `current` and
`DISPATCHER_BACKEND` selection.

Run the existing backend suite from the repository root:

```sh
PYTHONPATH=ai_agents_framework/docs_dispatcher/sources/backend python -m pytest ai_agents_framework/docs_dispatcher/sources/backend/mysql_persistent/tests
```

For this refactor, preserve all existing test cases and assertions. Only adapt
imports and monkeypatch module paths for the package rename; add no new tests.
