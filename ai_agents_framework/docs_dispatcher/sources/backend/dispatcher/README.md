# Dispatcher Backend Configuration

This directory is copied to `/etc/dispatcher` in the docs dispatcher image.
Mount a custom directory or volume there to override the bundled settings.

## Selecting a backend

The default backend is `mysql_persistent`, implemented by the Python package
of the same name. Dispatcher commands route to modules such as
`mysql_persistent.put_doc`.

- `current` contains the active specification, or may be a symlink to one of
  the specifications in `backends/`.
- `backends/mysql_persistent.yaml` contains the bundled persistent configuration.
- `DISPATCHER_SETTINGS_DIR` selects the settings directory; if it is unavailable,
  the bundled settings are used.
- `DISPATCHER_BACKEND`, when set, selects `backends/<name>.yaml` in that directory
  instead of `current`. Both command routing and backend configuration use it.
  Unset it to select through `current`.

Dispatcher Compose files set
`DISPATCHER_BACKEND: ${DISPATCHER_BACKEND:-mysql_persistent}` by default.
Custom backend specifications must declare the matching Python package in `name`.

## Persistent backend settings

The bundled settings retain the existing database and storage locations:

- `db_login_secret`: `/run/secrets/backend_mysql_db_login`
- `db_pwd_secret`: `/run/secrets/backend_mysql_db_password`
- `mysql_db_uri`: `sqlite:////mnt/file_storage/rag_docs_database.db`
- `storage_uri`: `/mnt/file_storage`

Database protocol names, credential fields and secret names still refer to MySQL;
these are independent of the backend implementation name.

## Filesystem storage

Each record directory is named for its database-generated ID. Metadata uses
`parentId`, `offset`, `size`, `metadata`, and `doc_type` files. Full documents
retain their encoded filename with the `.storage_bin` suffix; chunks retain
empty payload placeholders and refer to their parent's byte range.

`StorageRecordEntryInterface` owns directory creation, enumeration, deletion,
and metadata reads and writes. `PersistentStorageRecordEntry` inherits those
operations and alone defines `doc_suffix`, resolves document filenames, and
creates, reads, writes, or sizes document payloads. `StorageRecord` retains its
existing model API and delegates filesystem access to an entry.

A future nonpersistent entry can reuse directory and metadata operations without
inheriting any payload convention. It is not implemented here. Existing storage
requires no migration, and dispatcher command arguments and output are unchanged.
