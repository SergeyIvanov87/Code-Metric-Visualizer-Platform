# Dispatcher backend composition

`mysql_persistent` is the default backend. Its `MysqlPersistentBackend` implements
the abstract `Backend` contract and owns the lifecycle of the selected access and
store implementations; it contains no database, filesystem, or command operations.

## Layout

```text
backend/
├── dispatcher/                         # configuration, selection, BackendDispatcher
│   ├── current
│   └── backends/mysql_persistent.yaml
├── interfaces/
│   ├── backend/interface.py           # abstract Backend contract
│   ├── access/interface.py            # access contract
│   ├── schema/record.py                # shared RecordSchema
│   └── store/interface.py             # backend-neutral storage contract
├── interfaces_impl/
│   ├── access/mysql/                   # MysqlAccessRecordEntry and SQL models
│   └── store/persistent/               # PersistentStorageRecordEntry
└── mysql_persistent/backend.py          # concrete MysqlPersistentBackend composition
```

`BackendConfig` is data-only and `load_backend_config()` returns it.
`BackendDispatcher()` loads this configuration internally. Top-level
`sources/*.py` scripts use only the dispatcher and the selected interfaces:

```python
with BackendDispatcher().get_backend() as backend:
    result = backend.access.get_document_info(backend.store, document_ids)
```

`get_backend()` validates the selected `Backend` implementation, loads runtime
options, and delegates to its `create_instance()` factory. `MysqlPersistentBackend`
creates the store and access contexts and yields itself. The context closes the
database session and disposes its engine on exit. Top-level
scripts retain argument parsing, JSON/text output, and exit status handling; they
do not load configuration or know concrete implementations.

There is no `dispatcher/commands` directory, subprocess delegation, or
`interfaces/store/operations.py` helper layer. Command behavior belongs to the
two interface implementations. `mysql_persistent` implements the composition factory and owns both lifecycles.

## Interface responsibilities

| Interface | Operations |
| --- | --- |
| `AccessRecordEntryInterface` | Create a configured instance, resolve records, create documents, attach chunks, list documents, report document information, delete records, synchronize metadata |
| `StorageRecordEntryInterface` | Create a configured instance, manage directories and metadata, create documents/chunk placeholders, update chunk bounds, locate chunk data, retrieve documents/chunks |

MySQL access embeds the former CRUD functions as instance methods. There is no
separate `crud.py` forwarding layer. SQL execution, engine creation, schema
migration, and credentials remain private to the implementation; the generic
access contract exposes semantic operations and plain records. Implementation
utilities used by existing tests, such as rebuilding SQL metadata from a
directory, remain with MySQL access.

Cross-store operations receive the other interface explicitly. MySQL access
never imports a concrete store. Persistent retrieval obtains access records
through `AccessRecordEntryInterface`, validates consistency, and reads each
parent payload once for multiple requested chunks. Document and chunk creation
compensates for failures after ID allocation by removing partial file storage
first and then the database placeholder. Cleanup failures are included in the
operation error. This is still not a distributed
transaction: a process interruption can leave partial state, and deletion is
not atomic across database and filesystem.

Payload naming, creation, reading, writing, sizing, and mutable directory or
metadata operations belong to the persistent implementation. The store
interface contains only backend-neutral operations and its directory iteration
helper. Storage records are data-only; they do not select a backend or perform
filesystem operations. Unused model operations and duplicate interface
convenience methods have been removed. No nonpersistent implementation is added.

## Schemas

Both interfaces declare the shared `RecordSchema` through `record_schema`.

| Meaning | RecordSchema |
| --- | --- |
| ID | `id` |
| Document path | `file_uri` |
| Byte range | `offset`, `size` |
| Parent | `parent_id` |
| Metadata | `metadata` |
| Type | `doc_type` |

Access allocates IDs. A full document's parent ID equals its own ID; chunks
refer to a parent and byte range. The persistent layout is unchanged: numeric
record directories, `parentId`, `offset`, `size`, `metadata`, and `doc_type`
files, encoded payload filenames ending in `.storage_bin`, and empty chunk
payload placeholders. Existing documents require no migration.

## Configuration

Settings are copied to `/etc/dispatcher` in the image.

- `current` is the active specification or a symlink to one.
- `DISPATCHER_SETTINGS_DIR` selects the settings directory, falling back to the
  bundled settings when unavailable.
- `DISPATCHER_BACKEND` selects `backends/<name>.yaml` instead of `current`.
  Compose defaults it to `${DISPATCHER_BACKEND:-mysql_persistent}`.
- `name` selects the package exporting a concrete `Backend` implementation.
- `RuntimeConfig` contains only `options` and `spec_path`. All implementation
  settings, including `storage_uri`, are entries in `options`. Only the
  persistent store interprets and requires `storage_uri`.

Bundled options retain these values:

- `db_login_secret`: `/run/secrets/backend_mysql_db_login`
- `db_pwd_secret`: `/run/secrets/backend_mysql_db_password`
- `mysql_db_uri`: `sqlite:////mnt/file_storage/rag_docs_database.db`
- `storage_uri`: `/mnt/file_storage`

MySQL access also accepts `db_uri`. SQLite does not require credentials. Secret
names and MySQL protocol names are unchanged; credential source files now live
under `interfaces_impl/access/mysql/`.

## Existing tests

The same 20 backend cases now live under `tests/unit/cases`, registered through
`tests/unit/Dockerfile` and `init.sh`. No new test cases are added. Run from the
repository root:

```sh
docker compose -f ai_agents_framework/docs_dispatcher/compose-unit.test.yaml up --build --abort-on-container-exit --exit-code-from docs-dispatcher-unit-tester
```

For public filesystem API behavior, run the existing functional tester:

```sh
docker compose -f ai_agents_framework/docs_dispatcher/compose-functional.prod.yaml up --build --abort-on-container-exit --exit-code-from docs-dispatcher-functional-tester
```
