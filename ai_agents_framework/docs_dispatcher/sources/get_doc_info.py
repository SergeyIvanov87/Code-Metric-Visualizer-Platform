#!/usr/bin/env python

import argparse
import json
import subprocess
import sys

from dispatcher_backend_config import load_backend_config


def _parse_doc_ids(value: str) -> list[int]:
    values = value.split(",")
    if not value or any(not item.strip() for item in values):
        raise argparse.ArgumentTypeError("doc IDs must be a comma-separated list of integers")
    try:
        return [int(item.strip()) for item in values]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "doc IDs must be a comma-separated list of integers"
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="Get document information using assigned backend"
    )
    parser.add_argument("-doc_ids", "--doc_ids", required=True, type=_parse_doc_ids)
    args = parser.parse_args()

    backend_config = load_backend_config()
    command = [
        "python",
        "-m",
        backend_config.command_module("get_doc_info"),
        "--doc-ids",
        ",".join(str(doc_id) for doc_id in args.doc_ids),
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
            result = {"error_code": -1, "error_msg": exec_status.stdout}
    else:
        result = {"error_code": -1, "error_msg": exec_status.stderr}

    if exec_status.stderr and isinstance(result, dict) and "error_msg" not in result:
        result["error_msg"] = exec_status.stderr

    print(json.dumps(result))
    return exec_status.returncode


if __name__ == "__main__":
    sys.exit(main())
