#!/usr/bin/env python

import argparse
import json
import subprocess
import sys

from dispatcher_backend_config import load_backend_config


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
    backend_config = load_backend_config()
    command = [
        "python",
        "-m",
        backend_config.command_module("read_id"),
        "--id",
        str(record_id),
    ]
    exec_status = subprocess.run(
        command,
        capture_output=True,
        cwd=backend_config.backends_code_dir,
        text=True,
        shell=False,
    )

    if exec_status.stdout:
        try:
            result = json.loads(exec_status.stdout)
        except json.JSONDecodeError:
            result = {"id": record_id, "error_code": -1, "error_msg": exec_status.stdout}
    else:
        result = {"id": record_id, "error_code": -1, "error_msg": exec_status.stderr}

    if exec_status.stderr and isinstance(result, dict) and "error_msg" not in result:
        result["error_msg"] = exec_status.stderr

    context = result.get("context", "<Not found ID>")
    sys.stdout.write(context)
    return exec_status.returncode


if __name__ == "__main__":
    sys.exit(main())
