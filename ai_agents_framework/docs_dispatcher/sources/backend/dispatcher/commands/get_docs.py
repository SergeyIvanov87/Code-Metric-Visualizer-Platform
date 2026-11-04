#!/usr/bin/env python

import argparse
import json
import sys

from dispatcher.runtime import get_backend
from dispatcher.runtime_config import load_runtime_config
from interfaces.access import AccessRecordEntryInterface
from interfaces.access.utils import decanonize_file_uri


def get_documents(access: AccessRecordEntryInterface, offset: int = 0, limit: int = -1) -> dict[str, object]:
    if offset < 0:
        raise ValueError("offset must be greater than or equal to 0")
    if limit < -1:
        raise ValueError("limit must be -1 or greater")

    total_documents, document_rows = access.get_documents(offset, limit)
    documents = [
        {
            "id": int(document.id),
            "file_uri": decanonize_file_uri(document.file_path),
            "type": document.doc_type,
            "chunks": access.get_chunk_ids(document.id),
        }
        for document in document_rows
    ]
    returned_limit = len(documents)
    return {
        "offset": offset,
        "limit": returned_limit,
        "remaining": max(0, total_documents - offset - returned_limit),
        "docs": documents,
    }


def main():
    parser = argparse.ArgumentParser(prog="List documents using selected backend")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=-1)
    args = parser.parse_args()

    try:
        backend_config = load_runtime_config()
        with get_backend().access.open(backend_config) as access:
            result = get_documents(access, args.offset, args.limit)
        error_code = 0
    except Exception as ex:
        result = {"error_code": -1, "error_msg": str(ex)}
        error_code = -1

    print(json.dumps(result))
    return error_code


if __name__ == "__main__":
    sys.exit(main())
