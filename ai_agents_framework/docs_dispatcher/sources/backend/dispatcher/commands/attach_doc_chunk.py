#!/usr/bin/env python

import argparse
import base64
import json
import sys
from pathlib import Path

from dispatcher.runtime import get_backend
from dispatcher.runtime_config import load_runtime_config
from interfaces.store import operations as doc_storage_operations
from interfaces.store.models import StorageRecord
from interfaces.access.utils import prepare_doc_data

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
    parent_data = parent_storage_record.entry(storage_uri).read_document(parent_storage_record.file_uri)
    offset = parent_data.find(chunk_data)
    if offset < 0:
        raise ValueError("chunk does not belong to the parent document")
    return offset, len(chunk_data)


def main():
    parser = argparse.ArgumentParser(prog="Insert document chunk using selected backend")
    parser.add_argument("doc_id", type=int, help="Parent document id")
    parser.add_argument("-m", "--metadata", type=str, help="chunk metadata")

    args = parser.parse_args()
    backend_config = load_runtime_config()

    error_code = 0
    ret = {}
    try:
        stdin_stream = getattr(sys.stdin, "buffer", sys.stdin)
        chunk_data = stdin_stream.read()


        with get_backend().access.open(backend_config) as access:
            # read parent document first
            parent_db_record = access.get_file_record(args.doc_id)
            parent_storage_record = doc_storage_operations.get_record(backend_config.storage_uri, args.doc_id)

            if parent_db_record is None:
                raise ValueError(f"Parent document id={args.doc_id} does not exist in DB")
            if parent_storage_record is None:
                raise ValueError(f"Parent document id={args.doc_id} does not exist in storage")
            if parent_db_record.parent_id != parent_db_record.id:
                raise ValueError(f"Record id={args.doc_id} is not a full document")
            if parent_storage_record.parent_id != parent_storage_record.unique_id:
                raise ValueError(f"Storage record id={args.doc_id} is not a full document")


            # extract doc_type as a parent doc_type
            doc_type_array = parent_db_record.doc_type.split(',')
            if "base64" in doc_type_array:
                chunk_data = base64.b64decode(prepare_doc_data(chunk_data))
            else:
                chunk_data = prepare_doc_data(chunk_data)
            metadata_text = _read_metadata_text(args.metadata)

            created_db_record = None
            created_storage_record = None


            chunk_offset, chunk_size = _extract_chunk_bounds(backend_config.storage_uri, parent_storage_record, chunk_data)
            if parent_db_record.size >= 0 and chunk_offset + chunk_size > parent_db_record.size:
                raise ValueError(f"chunk with offset: {chunk_offset} and size: {chunk_size} does not fit into the parent document of size: {parent_db_record.size}, type: {parent_db_record.doc_type}")

            created_db_record = access.create_file_record(str(parent_db_record.file_path),
                0,
                0,
                parent_id_for_orphans,
                metadata_json={"comment": metadata_text},
            )

            try:
                created_storage_record = doc_storage_operations.add_abstract_chunk(
                    backend_config.storage_uri,
                    Path(str(parent_storage_record.file_uri)),
                    created_db_record.id,
                    metadata_text,
                )

                created_storage_record.update_record(
                    backend_config.storage_uri,
                    parent_id=args.doc_id,
                    offset_size=(chunk_offset, chunk_size),
                )
                created_db_record.offset = chunk_offset
                created_db_record.size = chunk_size
                created_db_record.parent_id = args.doc_id
                access.update_file_record_ext(created_db_record.id, created_db_record)
            except Exception:
                if created_storage_record is not None:
                    doc_storage_operations.delete_record(backend_config.storage_uri, created_storage_record.unique_id)
                if created_db_record is not None:
                    access.delete_file_record(created_db_record.id)
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
