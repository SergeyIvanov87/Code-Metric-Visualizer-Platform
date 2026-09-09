# Dispatcher Backend Configuration

This directory is copied to `/etc/dispatcher` in the docs dispatcher image.
Mount a custom directory or volume at `/etc/dispatcher` to override these
defaults without rebuilding the image.

## Layout

- `current`: active backend specification. It can be a copy of a file from
  `backends/*.yaml` or a symlink to the desired backend specification.
- `backends/*.yaml`: backend specifications.

## Backend Specification

Each backend YAML file declares the backend name and runtime properties used by
that backend implementation. The dispatcher entrypoints use only `name` for
routing and call same-named modules in the backend package, such as
`mysql.put_doc` for `put_doc.py`. Backend-specific modules read their own
runtime fields directly from this directory.

The default MySQL backend keeps the previous hardcoded values:

- `db_login_secret`: `/run/secrets/backend_mysql_db_login`
- `db_pwd_secret`: `/run/secrets/backend_mysql_db_password`
- `mysql_db_uri`: `sqlite:///rag_docs_database.db`
- `storage_uri`: `/package/file_storage`
