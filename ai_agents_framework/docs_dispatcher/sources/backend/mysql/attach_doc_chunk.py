#!/usr/bin/env python

import argparse
import json
import sys
from pathlib import Path

from mysql.app import crud
from mysql.app.database import Base, create_engine, create_session
from mysql.doc_storage import operations as doc_storage_operations
from mysql.doc_storage.fs_entity import StorageRecordEntry
from mysql.doc_storage.models import StorageRecord
from mysql.utils import prepare_doc_data

parent_id_for_orphans = 0


def _read_metadata_text(metadata_arg: str | None) -> str:
    if not metadata_arg:
        return ""

    metadata_path = Path(metadata_arg)
    if metadata_path.exists():
        return metadata_path.read_text()
    return metadata_arg


def _extract_chunk_bounds(
    storage_uri: Path,
    parent_storage_record: StorageRecord,
    chunk_data: bytes,
) -> tuple[int, int]:
    parent_doc_path = (storage_uri / str(parent_storage_record.unique_id) / parent_storage_record.file_uri).with_suffix(
        StorageRecordEntry.doc_suffix
    )
    parent_data = parent_doc_path.read_bytes()
    offset = parent_data.find(chunk_data)
    if offset < 0:
        raise ValueError("chunk does not belong to the parent document")
    return offset, len(chunk_data)


def main():
    parser = argparse.ArgumentParser(prog="Insert document chunk using MYSQL backend")
    parser.add_argument("login", type=Path, help="Login secret file path")
    parser.add_argument("pwd", type=Path, help="Password secret file path")
    parser.add_argument("db_uri", help="Database URI suffix (host/db)")
    parser.add_argument("storage_uri", type=Path, help="Path to local storage root")
    parser.add_argument("doc_id", type=int, help="Parent document id")
    parser.add_argument("-m", "--metadata", type=str, help="chunk metadata")

    args = parser.parse_args()

    stdin_stream = getattr(sys.stdin, "buffer", sys.stdin)
    chunk_data = stdin_stream.read()
    error_code = 0
    ret = {}
    try:
        chunk_data = prepare_doc_data(chunk_data)
        metadata_text = _read_metadata_text(args.metadata)

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

        created_db_record = None
        created_storage_record = None

        with create_session(engine) as session:
            parent_db_record = crud.get_file_record(session, args.doc_id)
            parent_storage_record = doc_storage_operations.get_record(args.storage_uri, args.doc_id)

            if parent_db_record is None:
                raise ValueError(f"Parent document id={args.doc_id} does not exist in DB")
            if parent_storage_record is None:
                raise ValueError(f"Parent document id={args.doc_id} does not exist in storage")
            if parent_db_record.parent_id != parent_db_record.id:
                raise ValueError(f"Record id={args.doc_id} is not a full document")
            if parent_storage_record.parent_id != parent_storage_record.unique_id:
                raise ValueError(f"Storage record id={args.doc_id} is not a full document")

            chunk_offset, chunk_size = _extract_chunk_bounds(args.storage_uri, parent_storage_record, chunk_data)
            if parent_db_record.size >= 0 and chunk_offset + chunk_size > parent_db_record.size:
                raise ValueError(f"chunk with offset: {chunk_offset} and size: {chunk_size} does not fit into the parent document of size: {parent_db_record.size}")

            created_db_record = crud.create_file_record(
                session,
                str(parent_db_record.file_path),
                0,
                0,
                parent_id_for_orphans,
                metadata_json={"comment": metadata_text},
            )

            try:
                created_storage_record = doc_storage_operations.add_abstract_chunk(
                    args.storage_uri,
                    Path(str(parent_storage_record.file_uri)),
                    created_db_record.id,
                    metadata_text,
                )

                created_storage_record.update_record(
                    args.storage_uri,
                    parent_id=args.doc_id,
                    offset_size=(chunk_offset, chunk_size),
                )
                created_db_record.offset = chunk_offset
                created_db_record.size = chunk_size
                created_db_record.parent_id = args.doc_id
                crud.update_file_record_ext(session, created_db_record.id, created_db_record)
            except Exception:
                if created_storage_record is not None:
                    doc_storage_operations.delete_record(args.storage_uri, created_storage_record.unique_id)
                if created_db_record is not None:
                    crud.delete_file_record(session, created_db_record.id)
                raise

            ret = {"unique_id": created_db_record.id if created_db_record is not None else 0}
    except Exception as ex:
        error_code = -1
        ret["error_msg"] = str(ex)

    ret["error_code"] = error_code
    print(json.dumps(ret))
    return error_code


if __name__ == "__main__":
    sys.exit(main())
