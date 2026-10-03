#!/usr/bin/env python

import argparse
import json
import subprocess
import sys

from dispatcher_backend_config import load_backend_config


def _parse_ids(value: str) -> list[int]:
    values = value.split(",")
    if not value or any(not item.strip() for item in values):
        raise argparse.ArgumentTypeError("IDs must be a comma-separated list of integers")
    try:
        return list(dict.fromkeys(int(item.strip()) for item in values))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "IDs must be a comma-separated list of integers"
        ) from exc


def _normalize_assignment_args(arguments: list[str]) -> list[str]:
    normalized: list[str] = []
    assignment_options = ("-ids", "--ids", "-metadata", "--metadata")
    for argument in arguments:
        if argument.startswith("SESSION_ID="):
            continue

        matched_option = next(
            (
                option
                for option in assignment_options
                if argument.startswith(f"{option}=")
            ),
            None,
        )
        if matched_option is None:
            normalized.append(argument)
            continue

        normalized.extend([matched_option, argument.split("=", 1)[1]])
    return normalized


def main():
    parser = argparse.ArgumentParser(prog="Delete documents or chunks using assigned backend")
    parser.add_argument("-ids", "--ids", required=True, type=_parse_ids, help="Record IDs")
    parser.add_argument("-metadata", "--metadata", type=str, help="delete metadata")

    args = parser.parse_args(_normalize_assignment_args(sys.argv[1:]))

    backend_config = load_backend_config()
    backends_path = backend_config.backends_code_dir

    sys.path.insert(0, str(backends_path))
    command = [
        "python",
        "-m",
        backend_config.command_module("delete_doc"),
        "-ids",
        ",".join(str(record_id) for record_id in args.ids),
    ]
    if args.metadata is not None:
        command.extend(["-m", args.metadata])

    exec_status = subprocess.run(
        command,
        capture_output=True,
        cwd=backends_path,
        text=False,
        shell=False,
    )
    return_data = {}
    err_str = exec_status.stderr.decode('utf-8')
    if err_str:
        return_data["error_msg"] = err_str

    output_str = exec_status.stdout.decode('utf-8')
    output = {}
    if output_str:
        output = json.loads(output_str)

    return_data = return_data | output
    print(json.dumps(return_data))


if __name__ == "__main__":
    sys.exit(main())
