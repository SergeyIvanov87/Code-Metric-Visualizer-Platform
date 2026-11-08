#!/usr/bin/env python

import argparse
import json
import sys

from dispatcher_backend_config import load_backend_config
from utils import get_impl_procedure_name

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
    command = backend_config.create_executable_command_prefix(get_impl_procedure_name(__file__))
    command.extend(["--doc-ids", ",".join(str(doc_id) for doc_id in args.doc_ids)])

    exec_status = backend_config.delegate_query(
        command,
        text=True,
    )

    return_data = backend_config.get_formatted_response(exec_status,
                                                        get_impl_procedure_name(__file__),
                                                        text=True)
    print(json.dumps(return_data))
    return exec_status.returncode


if __name__ == "__main__":
    sys.exit(main())
