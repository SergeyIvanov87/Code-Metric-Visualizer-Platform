#!/usr/bin/env python

import argparse
import json
import subprocess
import sys

from pathlib import Path

from dispatcher_backend_config import load_backend_config


def main():
    parser = argparse.ArgumentParser(prog="Insert document using assigned backend")
    parser.add_argument("-URI", "--URI", type=Path, help="file URI")
    parser.add_argument("-metadata", "--metadata", type=Path, help="file metadata")

    args = parser.parse_args()

    backend_config = load_backend_config()
    backends_path = backend_config.backends_code_dir

    sys.path.insert(0, str(backends_path))
    document_data = sys.stdin.read()

    # TODO base64 decode document_data
    command = [
        "python",
        "-m",
        backend_config.command_module("put_doc"),
        str(args.URI),
    ]
    if args.metadata is not None:
        command.extend(["-m", str(args.metadata)])

    exec_status = subprocess.run(
        command,
        input=document_data.encode(),
        capture_output=True,
        cwd=backends_path,
        text=False,
        shell=False,
    )

    out_output = exec_status.stdout.decode('utf-8').strip()
    output_msg = ""
    if out_output:
        output_msg = json.loads(out_output)

    return_data = {}
    return_data = return_data | output_msg
    print(json.dumps(return_data))


if __name__ == "__main__":
    sys.exit(main())
