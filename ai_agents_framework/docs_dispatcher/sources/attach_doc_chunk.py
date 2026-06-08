#!/usr/bin/env python

import argparse
import json
import subprocess
import sys

from dispatcher_backend_config import load_backend_config


def main():
    parser = argparse.ArgumentParser(prog="Attach document chunk using assigned backend")
    parser.add_argument("-doc_id", "--doc_id", type=int, help="Parent document id")
    parser.add_argument("-metadata", "--metadata", type=str, help="chunk metadata")

    args = parser.parse_args()

    backend_config = load_backend_config()
    backends_path = backend_config.backends_code_dir

    sys.path.insert(0, str(backends_path))
    chunk_data = sys.stdin.read()
    command = [
        "python",
        "-m",
        backend_config.command_module("attach_doc_chunk"),
        str(args.doc_id),
    ]
    if args.metadata is not None:
        command.extend(["-m", args.metadata])

    exec_status = subprocess.run(
        command,
        input=chunk_data.encode(),
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
