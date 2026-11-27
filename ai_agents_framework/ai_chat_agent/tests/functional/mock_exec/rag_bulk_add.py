#!/usr/bin/env python3

import argparse
import json
import os

from pathlib import Path

from mock_utils.mock_case import run
from mock_utils.parse_arguments import parse_arguments


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-directory", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-arguments", action="store_true")
    mode.add_argument("--prepare-api-channel", action="store_true")
    parser.add_argument("--initial-timeout")
    parser.add_argument("--update-timeout")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    arguments = (
        options.arguments[1:]
        if options.arguments[:1] == ["--"]
        else options.arguments
    )

    if options.check_arguments:
        try:
            session_id, _ = parse_arguments(arguments)
            if not session_id:
                raise ValueError("SESSION_ID is required")
        except ValueError as error:
            print(json.dumps({"error_code": -1, "error_msg": str(error)}))
            return 1
        print(json.dumps({"error_code": 0, "error_msg": "success"}))
        return 0

    if options.prepare_api_channel:
        staging = options.request_directory / "staging"
        events = options.request_directory / "events"
        staging.mkdir(mode=0o777)
        staging.chmod(0o777)
        os.mkfifo(events, 0o644)
        print(
            json.dumps(
                {
                    "input": str(staging),
                    "input_type": "DIRECTORY",
                    "staging": str(staging),
                    "events": str(events),
                    "events_type": "FIFO",
                    "protocol": "cmvp.rag-bulk-events.v1",
                }
            )
        )
        return 0

    return run("rag_bulk_add.json", arguments)


raise SystemExit(main())
