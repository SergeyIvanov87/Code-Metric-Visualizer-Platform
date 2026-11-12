#!/usr/bin/env python

import argparse
import json
import sys

from backend.dispatcher.dispatcher import BackendDispatcher

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
    parser = argparse.ArgumentParser(
        prog="Get document information using assigned backend"
    )
    parser.add_argument("-doc_ids", "--doc_ids", required=True, type=_parse_doc_ids)
    args = parser.parse_args()

    try:
        with BackendDispatcher().get_backend() as backend:
            result = backend.get_document_info(args.doc_ids)
        result = {"error_code": 0, **result}
    except Exception as ex:
        result = {"error_code": -1, "error_msg": str(ex)}
    print(json.dumps(result))
    return result["error_code"]


if __name__ == "__main__":
    sys.exit(main())
