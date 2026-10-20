# Dispatcher backend composition

The default backend is `mysql_persistent`. This name selects a composition of
record access and document storage; it is not a renamed database implementation.
The existing MySQL/SQLite operations live under `mysql_persistent/access`.

## Layout and responsibilities

```text
backend/
├── dispatcher/
│   ├── current
│   ├── backends/mysql_persistent.yaml
│   ├── config.py, runtime.py, runtime_config.py
│   ├── commands/
│   └── tests/
├── interfaces/
│   ├── access/             # AccessRecordEntryInterface, schema, utilities
│   └── store/              # StorageRecordEntryInterface, schema, operations
└── mysql_persistent/
    ├── __init__.py          # Binds the two implementations
    ├── access/              # MysqlAccessRecordEntry and legacy MySQL operations
    └── store/               # PersistentStorageRecordEntry
```

`mysql_persistent.backend` binds `MysqlAccessRecordEntry` as
`AccessRecordEntryInterface` and `PersistentStorageRecordEntry` as
`StorageRecordEntryInterface`. Only this composition imports both concrete
implementations. The MySQL access implementation has no dependency on persistent
storage. Dispatcher commands and common storage code use the interfaces and the
selected bindings, and contain no concrete implementation imports.

All public dispatcher scripts route to shared `dispatcher.commands` modules.
`dispatcher.runtime.get_backend()` loads the selected composition and checks its
two interface bindings. New backends implement these contracts and declare a
composition, without duplicating command scripts.

## Interface schemas

| Meaning | AccessRecord (`interfaces/access`) | StorageRecordSchema (`interfaces/store`) |
| --- | --- | --- |
| Record ID | `id` (allocated by access, required on persisted records) | `unique_id` |
| Document path | `file_path` (original URI) | `file_uri` (encoded filename when read from persistent storage) |
| Byte range | `offset`, `size` | `offset`, `size` |
| Parent document | `parent_id` | `parent_id` |
| Metadata | `metadata_json` | `metadata` |
| Document type | `doc_type` | `doc_type` |

A full document has its own ID as `parent_id`; a chunk refers to its parent's ID
and byte range. Both interfaces declare their schema through `record_schema`.

The access interface exposes semantic create, get, update, delete, pagination,
chunk lookup, and reconciliation operations. It returns plain records, not ORM
objects, query strings, engines, or cursors. A SQL or NoSQL implementation owns
connection setup, ID allocation, persistence, and query execution. Existing
metadata-preserving reconciliation behavior is retained.

The store interface provides directory and metadata utilities plus abstract
payload operations. Its persistent implementation alone defines `doc_suffix`
and creates, reads, writes, and sizes payload files. Common models delegate
through the selected store binding. A nonpersistent implementation is not part
of this change.

The on-disk layout is unchanged: database-generated numeric directories,
`parentId`, `offset`, `size`, `metadata`, and `doc_type` files, and encoded document
filenames ending in `.storage_bin`. Chunks retain empty payload placeholders.
Existing documents require no migration.

## Configuration

This directory is copied to `/etc/dispatcher` in the dispatcher image. Mount a
custom directory there to override bundled settings.

- `current` is the active specification, or a symlink to a backend specification.
- `DISPATCHER_SETTINGS_DIR` selects the settings directory, with bundled settings
  as fallback when the configured directory is unavailable.
- `DISPATCHER_BACKEND`, when set, selects `backends/<name>.yaml` instead of
  `current`. Compose defaults it to `${DISPATCHER_BACKEND:-mysql_persistent}`.
- `name` in the specification selects the composition package.
- `storage_uri` is the shared record storage root. Other fields are passed as
  opaque `RuntimeConfig.options` to the selected implementations. The dispatcher
  does not require SQL credentials or interpret database URI schemes.

The bundled composition retains these values:

- `db_login_secret`: `/run/secrets/backend_mysql_db_login`
- `db_pwd_secret`: `/run/secrets/backend_mysql_db_password`
- `mysql_db_uri`: `sqlite:////mnt/file_storage/rag_docs_database.db`
- `storage_uri`: `/mnt/file_storage`

MySQL access also accepts `db_uri`. Credential paths are used for MySQL
connections; SQLite does not require them. Secret names and MySQL protocol names
are unchanged. Compose credential source files now live in
`mysql_persistent/access/`.

## Existing checks

Run from the repository root with the backend directory on the import path:

```sh
PYTHONPATH=ai_agents_framework/docs_dispatcher/sources/backend python -m pytest -q ai_agents_framework/docs_dispatcher/sources/backend/dispatcher/tests
```

The existing cases and expected results are preserved. Tests use the access
adapter for shared command helpers and inject an access context for command
entrypoints. No new tests are added.
