#!/usr/bin/env python

import argparse
import json
import sys

from backend.dispatcher.dispatcher import BackendDispatcher
from utils import get_impl_procedure_name

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

    backend_dispatcher = BackendDispatcher()
    command = backend_dispatcher.create_executable_command_prefix(get_impl_procedure_name(__file__))
    command.extend(["--offset", str(offset)])
    command.extend(["--limit", str(limit)])

    exec_status = backend_dispatcher.delegate_query(
        command,
        text=True,
    )

    result = backend_dispatcher.get_formatted_response(exec_status,
                                                   get_impl_procedure_name(__file__),
                                                   text=True)
    print(json.dumps(result))
    return exec_status.returncode


if __name__ == "__main__":
    sys.exit(main())
