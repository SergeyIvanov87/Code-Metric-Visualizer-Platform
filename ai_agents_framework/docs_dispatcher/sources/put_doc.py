#!/usr/bin/env python

import argparse
import json
import sys

from pathlib import Path

from backend.dispatcher.dispatcher import BackendDispatcher

def main():
    parser = argparse.ArgumentParser(prog="Insert document using assigned backend")
    parser.add_argument("-URI", "--URI", type=Path, help="file URI")
    parser.add_argument("-metadata", "--metadata", type=str, default=None, help="file metadata")
    parser.add_argument("-doc_type", "--doc_type", type=str, default="txt", help="document type")

    args = parser.parse_args()
    try:
        if args.URI is None:
            stream = getattr(sys.stdin, "buffer", sys.stdin)
            data = stream.read()
            if isinstance(data, str):
                data = data.encode("utf-8")
        else:
            data = args.URI.read_bytes()
        with BackendDispatcher().get_backend() as backend:
            result = backend.access.put_doc(backend.store, args.URI, data,
                                            metadata_text=args.metadata or "", doc_type=args.doc_type or "")
        result = {"error_code": 0, **result}
    except Exception as ex:
        result = {"error_code": -1, "error_msg": str(ex)}
    print(json.dumps(result))
    return result["error_code"]


if __name__ == "__main__":
    sys.exit(main())
