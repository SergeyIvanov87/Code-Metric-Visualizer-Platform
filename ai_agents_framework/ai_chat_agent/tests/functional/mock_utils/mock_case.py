#!/usr/bin/env python3

import json

from pathlib import Path

from .log_exchange import log_exchange
from .parse_arguments import parse_arguments


def _matches_session(session_id, case_name):
    return session_id and (
        session_id == case_name
        or session_id.startswith(case_name + "_")
        or f"-{case_name}-" in session_id
    )


def run(case_file, arguments, extra=None, plain=False):
    query_name = Path(case_file).stem
    try:
        session_id, received = parse_arguments(arguments)
        if not session_id:
            raise ValueError("SESSION_ID is required")
        if extra:
            received.update(extra)
    except ValueError as error:
        print(json.dumps({"error_code": -1, "error_msg": str(error)}))
        return 1

    cases_path = Path(__file__).parents[1] / "api_test_cases" / case_file
    if not cases_path.is_file():
        answer = {
            "error_code": -1,
            "error_msg": f"mock case file does not exist: {case_file}",
        }
        log_exchange(session_id, query_name, received, None, answer)
        print(json.dumps(answer))
        return 1

    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    for case_name, candidates in cases.items():
        if not _matches_session(session_id, case_name):
            continue
        for stub in candidates if isinstance(candidates, list) else [candidates]:
            if received != stub["query_received"]:
                continue
            answer = stub["answer"]
            log_exchange(
                session_id,
                query_name,
                received,
                stub["query_received"],
                answer,
            )
            print(answer if plain else json.dumps(answer))
            return 0

    answer = {
        "error_code": -1,
        "error_msg": f"no stub data for the query: {received}",
    }
    log_exchange(session_id, query_name, received, None, answer)
    print(json.dumps(answer))
    return 1
