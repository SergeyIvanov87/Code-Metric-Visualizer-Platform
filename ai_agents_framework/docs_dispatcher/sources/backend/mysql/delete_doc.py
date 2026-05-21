#!/usr/bin/env python

import argparse
import json
import sys
from pathlib import Path

from mysql.app import crud
from mysql.app.database import Base, create_engine, create_session
from mysql.doc_storage import operations as doc_storage_operations


def _load_metadata_text(metadata_arg: str | None) -> str:
    if not metadata_arg:
        return ""

    metadata_path = Path(metadata_arg)
    if metadata_path.exists():
        return metadata_path.read_text()
    return metadata_arg


def _records_to_delete_query(record_id: int) -> str:
    return (
        "SELECT id, file_path, offset, size, parent_id, metadata_json "
        "FROM file_records "
        f"WHERE id = {record_id} OR parent_id = {record_id}"
    )


def _storage_delete_candidates(session, record_id: int) -> list[dict[str, object]]:
    result = crud.execute_query(session, _records_to_delete_query(record_id))
    return [dict(row._mapping) for row in result.fetchall()]


def _delete_sql(record_ids: list[int]) -> str:
    if not record_ids:
        return ""
    ids_csv = ", ".join(str(record_id) for record_id in record_ids)
    return f"DELETE FROM file_records WHERE id IN ({ids_csv})"


def main():
    parser = argparse.ArgumentParser(prog="Delete document or chunk using MYSQL backend")
    parser.add_argument("login", type=Path, help="Login secret file path")
    parser.add_argument("pwd", type=Path, help="Password secret file path")
    parser.add_argument("db_uri", help="Database URI suffix (host/db)")
    parser.add_argument("storage_uri", type=Path, help="Path to local storage root")
    parser.add_argument("id", type=int, help="Record id")
    parser.add_argument("-m", "--metadata", type=str, help="delete metadata")

    args = parser.parse_args()

    _ = _load_metadata_text(args.metadata)

    login = None
    password = None
    engine = None
    if args.db_uri.find("sqlite:///") == -1:
        login = args.login
        password = args.pwd
        engine = create_engine(login, password, args.db_uri)
    else:
        engine = create_engine(args.db_uri)

    Base.metadata.create_all(engine)
    deleted_from_storage = 0
    deleted_from_db = 0
    error_messages: list[str] = []
    try:
        with create_session(engine) as session:
            target_records = _storage_delete_candidates(session, args.id)
            if not target_records:
                raise ValueError(f"Record id={args.id} does not exist")

            deleted_ids: list[int] = []
            for record in target_records:
                record_id = int(record["id"])
                if doc_storage_operations.delete_record(args.storage_uri, record_id):
                    deleted_from_storage += 1
                deleted_ids.append(record_id)

            delete_query = _delete_sql(deleted_ids)
            if delete_query:
                crud.execute_query(session, delete_query)
                deleted_from_db += len(deleted_ids)
    except ValueError as ex:
        error_messages.append(str(ex))
        pass

    ret = {"deleted from DB": deleted_from_db, "deleted from storage": deleted_from_storage}
    error_code = 0
    if len(error_messages):
        error_code = 1
        ret["error_msg"] = "\n".join(error_messages)
    ret["error"] = error_code
    print(json.dumps(ret))
    return error_code


if __name__ == "__main__":
    sys.exit(main())
