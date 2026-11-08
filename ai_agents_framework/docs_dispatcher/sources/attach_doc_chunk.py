#!/usr/bin/env python

import argparse
import json
import sys

from dispatcher_backend_config import load_backend_config
from utils import get_impl_procedure_name

def main():
    parser = argparse.ArgumentParser(prog="Attach document chunk using assigned backend")
    parser.add_argument("-doc_id", "--doc_id", type=int, help="Parent document id")
    parser.add_argument("-metadata", "--metadata", type=str, default=None, help="chunk metadata")

    args = parser.parse_args()
    chunk_data = sys.stdin.read()
    chunk_data = chunk_data.encode('utf-8')

    backend_config = load_backend_config()
    command = backend_config.create_executable_command_prefix(get_impl_procedure_name(__file__))
    command.append(str(args.doc_id))
    if args.metadata is not None:
        command.extend(["-m", args.metadata])

    exec_status = backend_config.delegate_query(
        command,
        input_data=chunk_data,
        text=False
    )

    return_data = backend_config.get_formatted_response(exec_status,
                                                        get_impl_procedure_name(__file__),
                                                        text=False)
    print(json.dumps(return_data))
    return exec_status.returncode


if __name__ == "__main__":
    sys.exit(main())
