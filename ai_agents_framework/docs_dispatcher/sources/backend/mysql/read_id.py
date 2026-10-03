#!/usr/bin/env python

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from mysql.app.database import create_engine, create_session, initialize_schema
from mysql.app.models import FileRecord
from mysql.config import load_mysql_backend_config
from mysql.doc_storage import operations as doc_storage_operations
from mysql.doc_storage.models import StorageRecord


@dataclass(frozen=True)
class ResolvedRecord:
    record_id: int
    parent_id: int
    offset: int
    size: int

    @property
    def record_type(self) -> str:
        return "document" if self.parent_id == self.record_id else "chunk"

    @property
    def document_id(self) -> int:
        return self.record_id if self.record_type == "document" else self.parent_id


def _unique_ids(record_ids: Iterable[int]) -> list[int]:
    return list(dict.fromkeys(record_ids))


def _record_fields(record: FileRecord | StorageRecord) -> tuple[int, int, int]:
    return int(record.parent_id), int(record.offset), int(record.size)


def _resolve_records(
    session: Session,
    storage_records: dict[int, StorageRecord],
    record_ids: Iterable[int],
) -> tuple[dict[int, ResolvedRecord], dict[int, str]]:
    requested_ids = _unique_ids(record_ids)
    db_records = {
        int(record.id): record
        for record in session.query(FileRecord)
        .filter(FileRecord.id.in_(requested_ids))
        .all()
    }
    resolved: dict[int, ResolvedRecord] = {}
    errors: dict[int, str] = {}

    for record_id in requested_ids:
        db_record = db_records.get(record_id)
        storage_record = storage_records.get(record_id)
        if db_record is None and storage_record is None:
            errors[record_id] = f"Record id={record_id} does not exist"
            continue

        if db_record is not None and storage_record is not None:
            db_fields = _record_fields(db_record)
            storage_fields = _record_fields(storage_record)
            db_parent_id, db_offset, db_size = db_fields
            storage_parent_id, storage_offset, storage_size = storage_fields
            if db_parent_id != storage_parent_id:
                errors[record_id] = (
                    f"Record id={record_id} has inconsistent parent_id between DB "
                    "and file storage"
                )
                continue
            is_chunk = db_parent_id != record_id
            if is_chunk and (db_offset, db_size) != (storage_offset, storage_size):
                errors[record_id] = (
                    f"Chunk id={record_id} has inconsistent offset or size between DB "
                    "and file storage"
                )
                continue
            parent_id, offset, size = db_fields
        elif db_record is not None:
            parent_id, offset, size = _record_fields(db_record)
        else:
            parent_id, offset, size = _record_fields(storage_record)

        resolved[record_id] = ResolvedRecord(
            record_id=record_id,
            parent_id=parent_id,
            offset=offset,
            size=size,
        )

    return resolved, errors


def _payload_path(storage_uri: Path, document: StorageRecord) -> Path:
    return StorageRecord.canonize_file_uri(
        storage_uri / str(document.unique_id),
        Path(document.file_uri),
    )


def _read_document_payloads(
    storage_uri: Path,
    storage_records: dict[int, StorageRecord],
    document_ids: Iterable[int],
) -> tuple[dict[int, bytes], dict[int, str]]:
    payloads: dict[int, bytes] = {}
    errors: dict[int, str] = {}

    for document_id in _unique_ids(document_ids):
        document = storage_records.get(document_id)
        if document is None:
            errors[document_id] = (
                f"Parent document id={document_id} does not exist in file storage"
            )
            continue
        if document.parent_id != document.unique_id:
            errors[document_id] = (
                f"Parent id={document_id} does not identify a full document in file storage"
            )
            continue

        payload_path = _payload_path(storage_uri, document)
        try:
            payloads[document_id] = payload_path.read_bytes()
        except OSError as exc:
            errors[document_id] = (
                f"Cannot read parent document id={document_id} from file storage: {exc}"
            )

    return payloads, errors


def _extract_contexts(
    records: dict[int, ResolvedRecord],
    payloads: dict[int, bytes],
    payload_errors: dict[int, str],
) -> dict[int, dict[str, object]]:
    results: dict[int, dict[str, object]] = {}

    for record_id, record in records.items():
        payload_error = payload_errors.get(record.document_id)
        if payload_error is not None:
            results[record_id] = {
                "id": record_id,
                "error_code": -1,
                "status": "error",
                "error_msg": payload_error,
            }
            continue

        document_data = payloads[record.document_id]
        if record.record_type == "document":
            context_data = document_data
        else:
            if record.offset < 0 or record.size < 0:
                results[record_id] = {
                    "id": record_id,
                    "error_code": -1,
                    "status": "error",
                    "error_msg": (
                        f"Chunk id={record_id} has invalid offset={record.offset} "
                        f"or size={record.size}"
                    ),
                }
                continue
            chunk_end = record.offset + record.size
            if chunk_end > len(document_data):
                results[record_id] = {
                    "id": record_id,
                    "error_code": -1,
                    "status": "error",
                    "error_msg": (
                        f"Chunk id={record_id} range [{record.offset}, {chunk_end}) "
                        f"exceeds parent document size {len(document_data)}"
                    ),
                }
                continue
            context_data = document_data[record.offset:chunk_end]

        try:
            context = context_data.decode("utf-8")
        except UnicodeDecodeError as exc:
            results[record_id] = {
                "id": record_id,
                "error_code": -1,
                "status": "error",
                "error_msg": f"Record id={record_id} does not contain valid UTF-8 text: {exc}",
            }
            continue

        results[record_id] = {
            "id": record_id,
            "parent_id": record.parent_id,
            "record_type": record.record_type,
            "context": context,
            "error_code": 0,
            "status": "success",
        }

    return results


def read_ids(
    session: Session,
    storage_uri: Path,
    record_ids: Iterable[int],
) -> dict[int, dict[str, object]]:
    requested_ids = _unique_ids(record_ids)
    storage_records = doc_storage_operations.get_all_records(storage_uri)
    resolved, resolution_errors = _resolve_records(
        session,
        storage_records,
        requested_ids,
    )
    payloads, payload_errors = _read_document_payloads(
        storage_uri,
        storage_records,
        (record.document_id for record in resolved.values()),
    )
    results = _extract_contexts(resolved, payloads, payload_errors)

    for record_id, error_msg in resolution_errors.items():
        results[record_id] = {
            "id": record_id,
            "error_code": -1,
            "status": "error",
            "error_msg": error_msg,
        }

    return {record_id: results[record_id] for record_id in requested_ids}


def main() -> int:
    parser = argparse.ArgumentParser(prog="Read an ID using MYSQL backend")
    parser.add_argument("--id", required=True, type=int)
    args = parser.parse_args()

    try:
        backend_config = load_mysql_backend_config()
        if "sqlite:///" in backend_config.db_uri:
            engine = create_engine(backend_config.db_uri)
        else:
            engine = create_engine(
                backend_config.db_login_secret_path,
                backend_config.db_pwd_secret_path,
                backend_config.db_uri,
            )

        initialize_schema(engine)
        with create_session(engine) as session:
            result = read_ids(session, backend_config.storage_uri, [args.id])[args.id]
        return_code = 0 if result["error_code"] == 0 else -1
    except Exception as exc:
        result = {
            "id": args.id,
            "error_code": -1,
            "status": "error",
            "error_msg": str(exc),
        }
        return_code = -1

    print(json.dumps(result))
    return return_code


if __name__ == "__main__":
    sys.exit(main())
