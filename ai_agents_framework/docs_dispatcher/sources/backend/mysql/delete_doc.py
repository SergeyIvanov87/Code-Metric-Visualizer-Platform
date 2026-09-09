#!/usr/bin/env python

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from mysql.app import crud
from mysql.app.database import create_engine, create_session, initialize_schema
from mysql.config import load_mysql_backend_config
from mysql.doc_storage import operations as doc_storage_operations


def _load_metadata_text(metadata_arg: str | None) -> str:
    if not metadata_arg:
        return ""

    metadata_path = Path(metadata_arg)
    if metadata_path.exists():
        return metadata_path.read_text()
    return metadata_arg


def _unique_ids(record_ids: Iterable[int]) -> list[int]:
    return list(dict.fromkeys(record_ids))


def _parse_ids(value: str) -> list[int]:
    values = value.split(",")
    if not value or any(not item.strip() for item in values):
        raise argparse.ArgumentTypeError("IDs must be a comma-separated list of integers")
    try:
        return _unique_ids(int(item.strip()) for item in values)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "IDs must be a comma-separated list of integers"
        ) from exc


def _records_to_delete_query(record_ids: Iterable[int]) -> str:
    ids_csv = ", ".join(str(record_id) for record_id in _unique_ids(record_ids))
    return (
        "SELECT id, file_path, offset, size, parent_id, metadata_json "
        "FROM file_records "
        f"WHERE id IN ({ids_csv}) OR parent_id IN ({ids_csv})"
    )


def _storage_delete_candidates(
    session: Session,
    record_ids: Iterable[int],
) -> list[dict[str, object]]:
    result = crud.execute_query(session, _records_to_delete_query(record_ids))
    return [dict(row._mapping) for row in result.fetchall()]


def _delete_sql(record_ids: list[int]) -> str:
    if not record_ids:
        return ""
    ids_csv = ", ".join(str(record_id) for record_id in record_ids)
    return f"DELETE FROM file_records WHERE id IN ({ids_csv})"


def delete_records(
    session: Session,
    storage_uri: Path,
    record_ids: Iterable[int],
) -> tuple[int, int, list[int]]:
    requested_ids = _unique_ids(record_ids)
    target_records = _storage_delete_candidates(session, requested_ids)
    target_ids = _unique_ids(int(record["id"]) for record in target_records)
    target_id_set = set(target_ids)
    missing_ids = [record_id for record_id in requested_ids if record_id not in target_id_set]

    deleted_from_storage = 0
    for record_id in target_ids:
        if doc_storage_operations.delete_record(storage_uri, record_id):
            deleted_from_storage += 1

    delete_query = _delete_sql(target_ids)
    if delete_query:
        crud.execute_query(session, delete_query)

    return len(target_ids), deleted_from_storage, missing_ids


def main():
    parser = argparse.ArgumentParser(prog="Delete documents or chunks using MYSQL backend")
    parser.add_argument("-ids", required=True, type=_parse_ids, help="Record IDs")
    parser.add_argument("-m", "--metadata", type=str, help="delete metadata")

    args = parser.parse_args()
    backend_config = load_mysql_backend_config()

    _ = _load_metadata_text(args.metadata)

    login = None
    password = None
    engine = None
    if backend_config.db_uri.find("sqlite:///") == -1:
        login = backend_config.db_login_secret_path
        password = backend_config.db_pwd_secret_path
        engine = create_engine(login, password, backend_config.db_uri)
    else:
        engine = create_engine(backend_config.db_uri)

    initialize_schema(engine)
    deleted_from_storage = 0
    deleted_from_db = 0
    error_messages: list[str] = []
    try:
        with create_session(engine) as session:
            deleted_from_db, deleted_from_storage, missing_ids = delete_records(
                session,
                backend_config.storage_uri,
                args.ids,
            )
            error_messages.extend(
                f"Record id={record_id} does not exist" for record_id in missing_ids
            )
    except Exception as ex:
        error_messages.append(str(ex))
        pass

    ret = {"deleted from DB": deleted_from_db, "deleted from storage": deleted_from_storage}
    error_code = 0
    if len(error_messages):
        error_code = 1
        ret["error_msg"] = "\n".join(error_messages)
    ret["error_code"] = error_code
    print(json.dumps(ret))
    return error_code


if __name__ == "__main__":
    sys.exit(main())
