#!/usr/bin/env python

import argparse
import json
import sys

from pathlib import Path

from backend.dispatcher.dispatcher import BackendDispatcher

def main():
    parser = argparse.ArgumentParser(prog="Insert document using assigned backend")
    parser.add_argument("-URI", "--URI", type=str, help="required file URI")
    parser.add_argument("-metadata", "--metadata", type=str, default=None, help="file metadata")
    parser.add_argument("-doc_type", "--doc_type", type=str, default=None, help="document type (defaults to filename extension)")
    parser.add_argument("-preserveOriginal", "--preserveOriginal", type=int, default=1)

    args = parser.parse_args()
    result = {}
    try:
        if not args.URI:
            raise ValueError("URI is required")
        uri = Path(args.URI)
        with BackendDispatcher().get_backend() as backend:
            result = backend.put_doc_by_uri(
                uri,
                metadata_text=args.metadata or "",
                doc_type=args.doc_type or uri.suffix.lower().lstrip(".") or "txt",
                preserveOriginal=args.preserveOriginal,
            )
        result = {"error_code": 0, **result}
    except Exception as ex:
        result = {"error_code": -1, "error_msg": str(ex)}
    print(json.dumps(result))
    return result["error_code"]


if __name__ == "__main__":
    sys.exit(main())
