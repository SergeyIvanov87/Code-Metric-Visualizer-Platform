#!/usr/bin/env python

import argparse
import json
import sys

from backend.dispatcher.dispatcher import BackendDispatcher
from utils import get_impl_procedure_name

def main():
    parser = argparse.ArgumentParser(prog="Sync documents on a persistent storage")
    parser.parse_args()

    backend_dispatcher = BackendDispatcher()
    exec_status = backend_dispatcher.delegate_query(
        backend_dispatcher.create_executable_command_prefix(get_impl_procedure_name(__file__)),
        text=False,
    )

    return_data = backend_dispatcher.get_formatted_response(exec_status,
                                                            get_impl_procedure_name(__file__),
                                                            text=False)
    print(json.dumps(return_data))
    return exec_status.returncode



if __name__ == "__main__":
    sys.exit(main())
