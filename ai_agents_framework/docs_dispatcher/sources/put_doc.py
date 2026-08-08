#!/usr/bin/env python

import argparse
import base64
import json
import subprocess
import sys

from pathlib import Path

from dispatcher_backend_config import load_backend_config


def main():
    parser = argparse.ArgumentParser(prog="Insert document using assigned backend")
    parser.add_argument("-URI", "--URI", type=Path, help="file URI")
    parser.add_argument("-metadata", "--metadata", type=str, help="file metadata")

    args = parser.parse_args()
    metadata = args.metadata
    if args.URI is None:
        # read as is
        document_data = sys.stdin.read()
        document_data = document_data.encode()
    else:
        with open(args.URI,'rb') as f:
            document_data = f.read()
            if metadata.find("base64") == -1:
                metadata = "base64," + metadata
                document_data.base64.b64encode(document_data)

    backend_config = load_backend_config()
    backends_path = backend_config.backends_code_dir
    sys.path.insert(0, str(backends_path))

    command = [
        "python",
        "-m",
        backend_config.command_module("put_doc"),
        str(args.URI),
    ]
    if metadata is not None:
        command.extend(["-m", str(metadata)])

    exec_status = subprocess.run(
        command,
        input=document_data,
        capture_output=True,
        cwd=backends_path,
        text=False,
        shell=False,
    )

    output_msg = {}
    out_output = exec_status.stdout.decode('utf-8').strip()
    if out_output:
        output_msg = json.loads(out_output)

    return_data = {}
    return_data = return_data | output_msg
    print(json.dumps(return_data))


if __name__ == "__main__":
    sys.exit(main())
