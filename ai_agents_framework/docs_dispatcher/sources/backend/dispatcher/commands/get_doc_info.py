#!/usr/bin/env python

import argparse
import json
import sys
from pathlib import Path


from dispatcher.runtime import get_backend
from dispatcher.runtime_config import load_runtime_config
from interfaces.access import AccessRecord, AccessRecordEntryInterface
from interfaces.store import operations as doc_storage_operations
from interfaces.store.models import StorageRecord
from interfaces.access.utils import decanonize_file_uri


SUCCESS = "success"
MISSING_DATABASE = "Not found in the doc storage: database"
MISSING_FILE_STORAGE = "Not found in the doc storage: file storage"
ABSENT_OR_INVALID = "The doc is absent or ID is incorrect"


def _unique_ids(doc_ids: list[int]) -> list[int]:
    return list(dict.fromkeys(doc_ids))


def _is_db_document(record: AccessRecord | None, doc_id: int) -> bool:
    return record is not None and int(record.parent_id) == doc_id


def _is_storage_document(record: StorageRecord | None, doc_id: int) -> bool:
    return record is not None and record.parent_id == doc_id


def _db_info(
    access: AccessRecordEntryInterface,
    document: AccessRecord,
) -> dict[str, object]:
    chunks = access.get_chunk_ids(document.id)
    return {
        "file_uri": decanonize_file_uri(document.file_path),
        "type": document.doc_type,
        "chunks": chunks,
    }


def _storage_info(
    document: StorageRecord,
    storage_records: dict[int, StorageRecord],
) -> dict[str, object]:
    chunk_ids = sorted(
        record_id
        for record_id, record in storage_records.items()
        if record_id != document.unique_id and record.parent_id == document.unique_id
    )
    return {
        "file_uri": decanonize_file_uri(document.file_uri),
        "type": document.doc_type,
        "chunks": chunk_ids,
    }


def get_document_info(
    access: AccessRecordEntryInterface,
    storage_uri: Path,
    doc_ids: list[int],
) -> dict[str, object]:
    requested_ids = _unique_ids(doc_ids)
    storage_records = doc_storage_operations.get_all_records(storage_uri)
    found: list[int] = []
    inconsistent: list[int] = []
    not_found: list[int] = []
    result: dict[str, object] = {
        "found": found,
        "inconsistent": inconsistent,
        "not_found": not_found,
    }

    for doc_id in requested_ids:
        db_record = access.get_file_record(doc_id)
        storage_record = storage_records.get(doc_id)
        in_database = _is_db_document(db_record, doc_id)
        in_file_storage = _is_storage_document(storage_record, doc_id)

        if in_database and in_file_storage:
            found.append(doc_id)
            result[str(doc_id)] = {
                "error_code": 0,
                "status": SUCCESS,
                "info": _db_info(access, db_record),
            }
            continue

        if in_database:
            inconsistent.append(doc_id)
            result[str(doc_id)] = {
                "error_code": 1,
                "status": MISSING_FILE_STORAGE,
                "info": _db_info(access, db_record),
            }
        elif in_file_storage:
            inconsistent.append(doc_id)
            result[str(doc_id)] = {
                "error_code": 1,
                "status": MISSING_DATABASE,
                "info": _storage_info(storage_record, storage_records),
            }
        else:
            not_found.append(doc_id)
            result[str(doc_id)] = {
                "error_code": -1,
                "status": ABSENT_OR_INVALID,
            }

    return result


def _parse_doc_ids(value: str) -> list[int]:
    values = value.split(",")
    if not value or any(not item.strip() for item in values):
        raise argparse.ArgumentTypeError("doc IDs must be a comma-separated list of integers")
    try:
        return [int(item.strip()) for item in values]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "doc IDs must be a comma-separated list of integers"
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(prog="Get document information using selected backend")
    parser.add_argument("--doc-ids", required=True, type=_parse_doc_ids)
    args = parser.parse_args()

    try:
        backend_config = load_runtime_config()
        with get_backend().access.open(backend_config) as access:
            result = get_document_info(access, backend_config.storage_uri, args.doc_ids)
        return_code = 0
    except Exception as exc:
        result = {"error_code": -1, "error_msg": str(exc)}
        return_code = -1

    print(json.dumps(result))
    return return_code


if __name__ == "__main__":
    sys.exit(main())
