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

    selection = parameters["id"]
    batch = "," in selection or "-" in selection
    try:
        with BackendDispatcher().get_backend() as backend:
            records = backend.read_ids(selection)
        not_found = [
            record_id for record_id, record in records.items()
            if record.get("error_msg") == f"Record id={record_id} does not exist"
        ]
        missing_ids = set(not_found)
        unprocessed = [
            record_id for record_id, record in records.items()
            if record["error_code"] != 0 and record_id not in missing_ids
        ]
        result = {
            "error_code": -1 if unprocessed else 0,
            "not_found": not_found,
            "unprocessed": unprocessed,
            "records": records,
        }
    except Exception as error:
        result = {"error_code": -1, "error_msg": str(error)}
    if batch:
        print(json.dumps(result))
    else:
        record = result.get("records", {}).get(int(selection), {})
        sys.stdout.write(record.get("context", "<Not found ID>"))
    return result["error_code"]



if __name__ == "__main__":
    sys.exit(main())
