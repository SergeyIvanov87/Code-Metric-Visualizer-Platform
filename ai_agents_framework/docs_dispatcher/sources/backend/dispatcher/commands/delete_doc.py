#!/usr/bin/env python

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable


from dispatcher.runtime import get_backend
from dispatcher.runtime_config import load_runtime_config
from interfaces.access import AccessRecordEntryInterface
from interfaces.store import operations as doc_storage_operations


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


def delete_records(
    access: AccessRecordEntryInterface,
    storage_uri: Path,
    record_ids: Iterable[int],
) -> tuple[int, int, list[int]]:
    requested_ids = _unique_ids(record_ids)
    target_records = access.get_related_records(requested_ids)
    target_ids = _unique_ids(int(record.id) for record in target_records)
    target_id_set = set(target_ids)
    missing_ids = [record_id for record_id in requested_ids if record_id not in target_id_set]

    deleted_from_storage = 0
    for record_id in target_ids:
        if doc_storage_operations.delete_record(storage_uri, record_id):
            deleted_from_storage += 1

    if target_ids:
        access.delete_records(target_ids)

    return len(target_ids), deleted_from_storage, missing_ids


def main():
    parser = argparse.ArgumentParser(prog="Delete documents or chunks using selected backend")
    parser.add_argument("-ids", required=True, type=_parse_ids, help="Record IDs")
    parser.add_argument("-m", "--metadata", type=str, help="delete metadata")

    args = parser.parse_args()
    backend_config = load_runtime_config()

    _ = _load_metadata_text(args.metadata)

    deleted_from_storage = 0
    deleted_from_db = 0
    error_messages: list[str] = []
    try:
        with get_backend().access.open(backend_config) as access:
            deleted_from_db, deleted_from_storage, missing_ids = delete_records(
                access,
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
