#!/usr/bin/env python
"""Insert document bytes through the configured backend."""

import argparse
import json
import sys

from backend.dispatcher.dispatcher import BackendDispatcher


def main():
    parser = argparse.ArgumentParser(prog="Insert document data")
    parser.add_argument("--doc_type", help="required encoding and document type")
    parser.add_argument("--metadata", default="", help="document metadata")
    args = parser.parse_args()
    try:
        if not args.doc_type:
            raise ValueError("doc_type is required for document data")
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        data = stream.read()
        if isinstance(data, str):
            data = data.encode("utf-8")
        with BackendDispatcher().get_backend() as backend:
            result = backend.put_doc_by_data(
                None, data, metadata_text=args.metadata, doc_type=args.doc_type,
            )
        result = {"error_code": 0, **result}
    except Exception as error:
        result = {"error_code": -1, "error_msg": str(error)}
    print(json.dumps(result))
    return result["error_code"]


if __name__ == "__main__":
    sys.exit(main())
