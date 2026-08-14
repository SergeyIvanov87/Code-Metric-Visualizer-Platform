#!/usr/bin/env python

import argparse
import json
import re
import sys
from pathlib import Path

from fs_api_wrappers import (
    create_api_query_interruptible,
    execute_get_docs_query,
    generate_inner_session_id,
    get_normalized_api_queries,
)


def main(
    shared_api_dir: Path,
    main_service_name: str,
    sess_id: str,
    offset: int,
    limit: int,
):
    normalized_api_queries = get_normalized_api_queries(
        shared_api_dir,
        main_service_name,
        {
            "get_docs": re.compile(
                r".*ai_agent_rag_dispatcher.*get_docs.*"
            ),
        },
    )

    session_id = generate_inner_session_id(sess_id, "get_docs")
    get_docs_query = create_api_query_interruptible(
        shared_api_dir, normalized_api_queries["get_docs"], session_id
    )

    return execute_get_docs_query(
        get_docs_query,
        session_id,
        timeout_elapsed=10,
        offset=offset,
        limit=limit,
    )


def parse_parameters(parameters):
    if len(parameters) % 2 != 0:
        raise ValueError("parameters must be provided as name/value pairs")

    parsed_parameters = dict(zip(parameters[::2], parameters[1::2]))
    unexpected_parameters = set(parsed_parameters) - {"offset", "limit"}
    if unexpected_parameters:
        unexpected = ", ".join(sorted(unexpected_parameters))
        raise ValueError(f"unexpected parameters: {unexpected}")
    if "offset" not in parsed_parameters or "limit" not in parsed_parameters:
        raise ValueError("both offset and limit parameters are required")

    return int(parsed_parameters["offset"]), int(parsed_parameters["limit"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="List RAG documents")
    parser.add_argument(
        "shared_api_dir", type=Path, help="Root path of the mounted API dir"
    )
    parser.add_argument("main_service_name", type=str, help="the main service name")
    parser.add_argument(
        "-session_id", "--session_id", type=str, help="Session identifier"
    )
    parser.add_argument("parameters", nargs="*")
    args = parser.parse_args()

    error_code = 0
    try:
        offset, limit = parse_parameters(args.parameters)
        result = main(
            args.shared_api_dir,
            args.main_service_name,
            args.session_id,
            offset,
            limit,
        )
    except Exception as ex:
        error_code = -1
        result = {
            "error_code": error_code,
            "error_msg": f"Couldn't get RAG documents, error: {ex}",
        }

    print(json.dumps(result))
    sys.exit(error_code)
