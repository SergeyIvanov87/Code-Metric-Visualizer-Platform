#!/usr/bin/env python

import argparse
from contextlib import ExitStack
import json
import sys
from pathlib import Path
from typing import Any, TypedDict


from dispatcher.runtime import get_backend
from dispatcher.runtime_config import load_runtime_config
from interfaces.access import AccessRecord, AccessRecordEntryInterface
from interfaces.store import operations as doc_storage_operations
from interfaces.store.models import StorageRecord
from interfaces.access.utils import decanonize_file_uri, file_uris_equal


class SyncResult(TypedDict):
    created: int
    updated: int
    deleted: int
    not_changed: int


def _storage_file_uri(storage_record: StorageRecord) -> str:
    # Records read from storage contain the filesystem-safe filename. Decode it
    # only at the DB boundary so AccessRecord always retains the original URI.
    return decanonize_file_uri(str(storage_record.file_uri))


def apply_storage_fields_to_db_record(
    db_record: AccessRecord,
    storage_record: StorageRecord,
) -> tuple[bool, AccessRecord]:
    changed = False

    storage_path = _storage_file_uri(storage_record)
    if not file_uris_equal(db_record.file_path, storage_record.file_uri):
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
    if db_record.doc_type != storage_record.doc_type:
        db_record.doc_type = storage_record.doc_type
        changed = True

    return changed, db_record


def synchronize_records(
    access: AccessRecordEntryInterface,
    all_db_records: list[AccessRecord],
    storage_records: dict[int, StorageRecord],
) -> SyncResult:
    remaining_storage = dict(storage_records)

    deleted = 0
    updated = 0
    untouched = len(remaining_storage)

    db_records_to_update: list[AccessRecord] = []
    for db_record in all_db_records:
        if db_record.id not in remaining_storage:
            access.delete_file_record(db_record.id)
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
            access.update_file_record_ext(db_record.id, db_record)
            updated += 1

        remaining_storage.pop(db_record.id)

    created = len(remaining_storage)
    untouched = untouched - updated - created

    for storage_record in remaining_storage.values():
        access.create_file_record_with_uid(storage_record.unique_id,
            _storage_file_uri(storage_record),
            storage_record.offset,
            storage_record.size,
            storage_record.parent_id,
            metadata_json=storage_record.metadata,
            doc_type=storage_record.doc_type,
        )

    return {
        "created": created,
        "updated": updated,
        "deleted": deleted,
        "not_changed": untouched,
    }


def synchronize_from_file_storage(
    access: AccessRecordEntryInterface,
    storage_uri: Path,
) -> dict[str, Any]:
    all_db_records = access.get_all_records()
    all_storage_records = doc_storage_operations.get_all_records(storage_uri)
    sync_result = synchronize_records(access, all_db_records, all_storage_records)

    return {
        **sync_result,
        "initial DB records": len(all_db_records),
        "storage size": len(all_storage_records),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="Dispatcher backend interaction")

    parser.parse_args(argv)
    backend_config = load_runtime_config()

    with ExitStack() as stack:
        try:
            access = stack.enter_context(get_backend().access.open(backend_config))
        except Exception as ex:
            print(str(ex), file=sys.stderr, flush=True)
            return -1

        get_backend().store(backend_config.storage_uri).ensure_root()
        result = {}
        try:
            result = synchronize_from_file_storage(access, backend_config.storage_uri)
        except Exception as ex:
            result["error_code"] = -1
            result["error_msg"] = str(ex)
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
