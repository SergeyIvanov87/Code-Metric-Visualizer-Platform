#!/usr/bin/env python

import argparse
import json
import sys

from backend.dispatcher.dispatcher import BackendDispatcher
from utils import get_impl_procedure_name

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
    backend_dispatcher = BackendDispatcher()
    command = backend_dispatcher.create_executable_command_prefix(get_impl_procedure_name(__file__))
    command.extend(["--id", str(record_id)])
    exec_status = backend_dispatcher.delegate_query(
        command,
        text=True,
    )

    result = backend_dispatcher.get_formatted_response(exec_status,
                                                   get_impl_procedure_name(__file__),
                                                   text=True)
    result["id"] = record_id

    context = result.get("context", "<Not found ID>")
    sys.stdout.write(context)
    return exec_status.returncode


if __name__ == "__main__":
    sys.exit(main())
