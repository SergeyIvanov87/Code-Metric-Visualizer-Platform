#!/usr/bin/env python

import json
import sys

from pathlib import Path

from log_exchange import log_exchange
from parse_arguments import parse_arguments


if __name__ == "__main__":
    cases_path = Path(__file__).parents[1] / "api_test_cases" / "put_doc.json"
    with cases_path.open(encoding="utf-8") as cases_file:
        cases = json.load(cases_file)

    try:
        session_id, received = parse_arguments(sys.argv[1:])
    except ValueError as error:
        print(json.dumps({"error_code": -1, "error_msg": str(error)}))
        sys.exit(1)

    for case_name, case in cases.items():
        if session_id and not (
            session_id == case_name or session_id.startswith(f"{case_name}_")
        ):
            continue
        for stub in case if isinstance(case, list) else [case]:
            if received == stub["query_received"]:
                answer = stub["answer"]
                log_exchange(received, stub["query_received"], answer)
                print(json.dumps(answer))
                sys.exit(0)

    answer = {
        "error_code": -1,
        "error_msg": f"no stub data for the query: {received}",
    }
    log_exchange(received, None, answer)
    print(json.dumps(answer))
    sys.exit(1)
