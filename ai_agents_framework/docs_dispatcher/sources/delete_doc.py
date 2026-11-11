#!/usr/bin/env python

import argparse
import json
import sys

from backend.dispatcher.dispatcher import BackendDispatcher
from utils import read_metadata_text

def _parse_ids(value: str) -> list[int]:
    values = value.split(",")
    if not value or any(not item.strip() for item in values):
        raise argparse.ArgumentTypeError("IDs must be a comma-separated list of integers")
    try:
        return list(dict.fromkeys(int(item.strip()) for item in values))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "IDs must be a comma-separated list of integers"
        ) from exc


def _normalize_assignment_args(arguments: list[str]) -> list[str]:
    normalized: list[str] = []
    assignment_options = ("-ids", "--ids", "-metadata", "--metadata")
    for argument in arguments:
        if argument.startswith("SESSION_ID="):
            continue

        matched_option = next(
            (
                option
                for option in assignment_options
                if argument.startswith(f"{option}=")
            ),
            None,
        )
        if matched_option is None:
            normalized.append(argument)
            continue

        normalized.extend([matched_option, argument.split("=", 1)[1]])
    return normalized


def main():
    parser = argparse.ArgumentParser(prog="Delete documents or chunks using assigned backend")
    parser.add_argument("-ids", "--ids", required=True, type=_parse_ids, help="Record IDs")
    parser.add_argument("-metadata", "--metadata", type=str, help="delete metadata")

    args = parser.parse_args(_normalize_assignment_args(sys.argv[1:]))

    deleted_db = deleted_storage = 0
    try:
        read_metadata_text(args.metadata)
        with BackendDispatcher().get_backend() as backend:
            deleted_db, deleted_storage, missing_ids = backend.delete_records(args.ids)
        errors = [f"Docs id={record_id} does not exist" for record_id in missing_ids]
    except Exception as ex:
        errors = [str(ex)]
    result = {"deleted from DB": deleted_db, "deleted from storage": deleted_storage,
              "error_code": 1 if errors else 0}
    if errors:
        result["error_msg"] = "\n".join(errors)
    print(json.dumps(result))
    return result["error_code"]


if __name__ == "__main__":
    sys.exit(main())
