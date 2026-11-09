#!/usr/bin/env python

import argparse
import json
import sys

from backend.dispatcher.dispatcher import BackendDispatcher

def main() -> int:
    parser = argparse.ArgumentParser(prog="Read an ID using assigned backend")
    parser.add_argument("parameters", nargs="*")
    args = parser.parse_args()

    if len(args.parameters) % 2 != 0:
        parser.error("parameters must be provided as name/value pairs")

    parameters = dict(zip(args.parameters[::2], args.parameters[1::2]))
    unexpected_parameters = set(parameters) - {"id"}
    if unexpected_parameters:
        parser.error(f"unexpected parameters: {', '.join(sorted(unexpected_parameters))}")
    if "id" not in parameters:
        parser.error("id parameter is required")

    record_id = int(parameters["id"])
    try:
        with BackendDispatcher().get_backend() as backend:
            result = backend.store.read_ids(backend.access, [record_id])[record_id]
    except Exception:
        result = {"error_code": -1}
    sys.stdout.write(result.get("context", "<Not found ID>"))
    return 0 if result["error_code"] == 0 else -1


if __name__ == "__main__":
    sys.exit(main())
