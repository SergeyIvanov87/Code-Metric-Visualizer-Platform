#!/usr/bin/env python

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, TypedDict

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from mysql.app import crud
from mysql.app.database import Base, create_engine, create_session
from mysql.app.models import FileRecord
from mysql.config import load_mysql_backend_config
from mysql.doc_storage import operations as doc_storage_operations
from mysql.doc_storage.models import StorageRecord


class SyncResult(TypedDict):
    created: int
    updated: int
    deleted: int
    not_changed: int


def _storage_file_uri(storage_record: StorageRecord) -> str:
    file_uri = storage_record.file_uri
    return str(file_uri)


def apply_storage_fields_to_db_record(
    db_record: FileRecord,
    storage_record: StorageRecord,
) -> tuple[bool, FileRecord]:
    changed = False

    storage_path = _storage_file_uri(storage_record)
    if db_record.file_path != storage_path:
        db_record.file_path = storage_path
        changed = True
    if db_record.offset != storage_record.offset:
        db_record.offset = storage_record.offset
        changed = True
    if db_record.size != storage_record.size:
        db_record.size = storage_record.size
        changed = True
    if db_record.parent_id != storage_record.parent_id:
        db_record.parent_id = storage_record.parent_id
        changed = True

    return changed, db_record


def synchronize_records(
    session: Session,
    all_db_records: list[FileRecord],
    storage_records: dict[int, StorageRecord],
) -> SyncResult:
    remaining_storage = dict(storage_records)

    deleted = 0
    updated = 0
    untouched = len(remaining_storage)

    db_records_to_update: list[FileRecord] = []
    for db_record in all_db_records:
        if db_record.id not in remaining_storage:
            crud.delete_file_record(session, db_record.id)
            deleted += 1
            continue
        db_records_to_update.append(db_record)

    for db_record in db_records_to_update:
        storage_record = remaining_storage[db_record.id]
        is_updated, db_record = apply_storage_fields_to_db_record(
            db_record,
            storage_record,
        )
        if is_updated:
            crud.update_file_record_ext(session, db_record.id, db_record)
            updated += 1

        remaining_storage.pop(db_record.id)

    created = len(remaining_storage)
    untouched = untouched - updated - created

    for storage_record in remaining_storage.values():
        crud.create_file_record_with_uid(
            session,
            storage_record.unique_id,
            _storage_file_uri(storage_record),
            storage_record.offset,
            storage_record.size,
            storage_record.parent_id,
        )

    return {
        "created": created,
        "updated": updated,
        "deleted": deleted,
        "not_changed": untouched,
    }


def synchronize_from_file_storage(
    engine: Engine,
    storage_uri: Path,
) -> dict[str, Any]:
    with create_session(engine) as session:
        all_db_records = crud.get_all_records(session)
        all_storage_records = doc_storage_operations.get_all_records(storage_uri)
        sync_result = synchronize_records(
            session,
            all_db_records,
            all_storage_records,
        )

    return {
        **sync_result,
        "initial DB records": len(all_db_records),
        "storage size": len(all_storage_records),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="MYSQL backend interaction")

    parser.parse_args(argv)
    backend_config = load_mysql_backend_config()

    engine = None
    try:
        if backend_config.db_uri.find("sqlite:///") == -1:
            engine = create_engine(
                backend_config.db_login_secret_path,
                backend_config.db_pwd_secret_path,
                backend_config.db_uri,
            )
        else:
            engine = create_engine(backend_config.db_uri)

        Base.metadata.create_all(engine)
    except Exception as ex:
        print(f"{str(ex)}", file=sys.stderr, flush=True)
        return -1

    os.makedirs(backend_config.storage_uri, mode=0o777, exist_ok=True)
    result = synchronize_from_file_storage(engine, backend_config.storage_uri)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
