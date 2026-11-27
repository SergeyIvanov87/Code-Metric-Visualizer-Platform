#!/usr/bin/env python3

import json
import sys

from pathlib import Path

from mock_utils.log_exchange import log_exchange
from mock_utils.parse_arguments import parse_arguments


CASES_PATH = Path(__file__).parents[1] / "api_test_cases" / "read_id.json"
DATA_PATH = Path(__file__).parents[1] / "rag_data"


def _matches_session(session_id, case_name):
    return session_id and (
        session_id == case_name
        or session_id.startswith(case_name + "_")
        or f"-{case_name}-" in session_id
    )


def main(arguments):
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    try:
        session_id, received = parse_arguments(arguments)
    except ValueError as error:
        print(json.dumps({"error_code": -1, "error_msg": str(error)}))
        return 1

    for case_name, candidates in cases.items():
        if not _matches_session(session_id, case_name):
            continue
        for stub in candidates if isinstance(candidates, list) else [candidates]:
            if received != stub["query_received"]:
                continue
            fixture_name = f"{received['id']}.txt"
            if stub["answer"] != {"fixture": fixture_name}:
                raise RuntimeError(
                    f"read_id case must map id {received['id']} to {fixture_name}"
                )
            answer = (DATA_PATH / fixture_name).read_text(encoding="utf-8")
            log_exchange(
                session_id,
                "read_id",
                received,
                stub["query_received"],
                answer,
            )
            print(answer)
            return 0

    answer = {
        "error_code": -1,
        "error_msg": f"no stub data for the query: {received}",
    }
    log_exchange(session_id, "read_id", received, None, answer)
    print(json.dumps(answer))
    return 1


raise SystemExit(main(sys.argv[1:]))
