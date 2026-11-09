#!/usr/bin/env python

import argparse
import json
import sys

from backend.dispatcher.dispatcher import BackendDispatcher
from utils import read_metadata_text

def main():
    parser = argparse.ArgumentParser(prog="Attach document chunk using assigned backend")
    parser.add_argument("-doc_id", "--doc_id", type=int, help="Parent document id")
    parser.add_argument("-metadata", "--metadata", type=str, default=None, help="chunk metadata")

    args = parser.parse_args()
    stream = getattr(sys.stdin, "buffer", sys.stdin)
    chunk_data = stream.read()
    if isinstance(chunk_data, str):
        chunk_data = chunk_data.encode("utf-8")
    try:
        with BackendDispatcher().get_backend() as backend:
            result = backend.access.attach_doc_chunk(backend.store, args.doc_id, chunk_data, metadata_text=read_metadata_text(args.metadata))
        result = {"error_code": 0, **result}
    except Exception as ex:
        result = {"error_code": -1, "error_msg": str(ex)}
    print(json.dumps(result))
    return result["error_code"]


if __name__ == "__main__":
    sys.exit(main())
