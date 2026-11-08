#!/usr/bin/env python

import argparse
import json
import sys

from dispatcher_backend_config import load_backend_config
from utils import get_impl_procedure_name

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
    command = backend_config.create_executable_command_prefix(get_impl_procedure_name(__file__))
    command.extend(["-ids", ",".join(str(record_id) for record_id in args.ids)])
    if args.metadata is not None:
        command.extend(["-m", args.metadata])

    exec_status = backend_config.delegate_query(
        command,
        text=False
    )

    return_data = backend_config.get_formatted_response(exec_status,
                                                        get_impl_procedure_name(__file__),
                                                        text=False)
    print(json.dumps(return_data))
    return exec_status.returncode

if __name__ == "__main__":
    sys.exit(main())
