#!/usr/bin/env python

import argparse
import json
import sys

from backend.dispatcher.dispatcher import BackendDispatcher

def main():
    parser = argparse.ArgumentParser(
        prog="List documents using assigned backend",
        usage="%(prog)s offset OFFSET limit LIMIT",
    )
    parser.add_argument("parameters", nargs="*")
    args = parser.parse_args()

    if len(args.parameters) % 2 != 0:
        parser.error("parameters must be provided as name/value pairs")

    parameters = dict(zip(args.parameters[::2], args.parameters[1::2]))
    unexpected_parameters = set(parameters) - {"offset", "limit"}
    if unexpected_parameters:
        parser.error(f"unexpected parameters: {', '.join(sorted(unexpected_parameters))}")
    if "offset" not in parameters or "limit" not in parameters:
        parser.error("both offset and limit parameters are required")

    offset = int(parameters["offset"])
    limit = int(parameters["limit"])

    try:
        with BackendDispatcher().get_backend() as backend:
            result = backend.access.get_documents(offset, limit)
        result = {"error_code": 0, **result}
    except Exception as ex:
        result = {"error_code": -1, "error_msg": str(ex)}
    print(json.dumps(result))
    return result["error_code"]


if __name__ == "__main__":
    sys.exit(main())
