#!/usr/bin/env python

import argparse
import json
import subprocess
import sys

from dispatcher_backend_config import load_backend_config


def main():
    parser = argparse.ArgumentParser(prog="Sync documents on a persistent storage")
    parser.parse_args()

    backend_config = load_backend_config()
    backends_path = backend_config.backends_code_dir

    sys.path.insert(0, str(backends_path))
    exec_status = subprocess.run(
        [
            "python",
            "-m",
            backend_config.command_module("sync"),
        ],
        capture_output=True,
        cwd=backends_path,
        text=False,
        shell=False,
    )

    error_output = exec_status.stderr.decode('utf-8').strip()
    error_msg = ""
    if error_output:
        error_msg = str(error_output)#json.loads(error_output)

    out_output = exec_status.stdout.decode('utf-8').strip()
    output_msg = ""
    if out_output:
        output_msg = json.loads(out_output)

    return_data = {"error_code": exec_status.returncode, "error_msg": error_msg, "output": output_msg}
    print(json.dumps(return_data))



if __name__ == "__main__":
    sys.exit(main())
