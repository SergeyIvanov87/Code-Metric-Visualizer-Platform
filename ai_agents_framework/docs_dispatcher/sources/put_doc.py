#!/usr/bin/env python

import argparse
import json
import sys

from pathlib import Path

from backend.dispatcher.dispatcher import BackendDispatcher
from dispatcher_backend_config import load_backend_config
from utils import get_impl_procedure_name

def main():
    parser = argparse.ArgumentParser(prog="Insert document using assigned backend")
    parser.add_argument("-URI", "--URI", type=Path, help="file URI")
    parser.add_argument("-metadata", "--metadata", type=str, default=None, help="file metadata")
    parser.add_argument("-doc_type", "--doc_type", type=str, default="txt", help="document type")

    return_data = {'error_code' : 0}
    try:
        args = parser.parse_args()
        metadata = args.metadata
        doc_type = args.doc_type
        document_data = None
        if args.URI is None:
            # read as is
            document_data = sys.stdin.buffer.read()

        backend_config = load_backend_config()
        backend_dispatcher = BackendDispatcher(backend_config)
        command = backend_dispatcher.create_executable_command_prefix(get_impl_procedure_name(__file__))
        if args.URI is not None:
            command.append(str(args.URI))

        if metadata is not None:
            command.extend(["-m", str(metadata)])

        if doc_type is not None:
            command.extend(["-doc_type", str(doc_type)])

        exec_status = backend_dispatcher.delegate_query(
            command,
            input_data=document_data,
            text=False,
        )

        return_data = backend_dispatcher.get_formatted_response(exec_status,
                                                            get_impl_procedure_name(__file__),
                                                            text=False)
    except Exception as ex:
        return_data["error_code"] = -1
        return_data["error_msg"] = str(ex)

    print(json.dumps(return_data))
    return return_data["error_code"]


if __name__ == "__main__":
    sys.exit(main())
