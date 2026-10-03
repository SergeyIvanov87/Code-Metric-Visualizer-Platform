#!/usr/bin/env python

import argparse
import json
import subprocess
import sys

from dispatcher_backend_config import load_backend_config


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

    backend_config = load_backend_config()
    backends_path = backend_config.backends_code_dir
    command = [
        "python",
        "-m",
        backend_config.command_module("get_docs"),
        "--offset",
        str(offset),
        "--limit",
        str(limit),
    ]

    exec_status = subprocess.run(
        command,
        capture_output=True,
        cwd=backends_path,
        text=True,
        shell=False,
    )

    if exec_status.stdout:
        try:
            result = json.loads(exec_status.stdout)
        except json.JSONDecodeError:
            result = {"error_code": -1, "error_msg": exec_status.stdout}
    else:
        result = {"error_code": -1, "error_msg": exec_status.stderr}

    if exec_status.stderr and isinstance(result, dict) and "error_msg" not in result:
        result["error_msg"] = exec_status.stderr

    print(json.dumps(result))
    return exec_status.returncode


if __name__ == "__main__":
    sys.exit(main())
