#!/usr/bin/env python3
import json
from pathlib import Path
from .log_exchange import log_exchange
from .parse_arguments import parse_arguments

def run(case_file, arguments, extra=None, plain=False):
    query_name = Path(case_file).stem
    cases = json.loads((Path(__file__).parents[1] / "api_test_cases" / case_file).read_text())
    try:
        session_id, received = parse_arguments(arguments)
        if extra:
            received.update(extra)
    except ValueError as error:
        print(json.dumps({"error_code": -1, "error_msg": str(error)}))
        return 1
    for case_name, case in cases.items():
        if session_id and not (session_id == case_name or session_id.startswith(case_name + "_") or f"-{case_name}-" in session_id):
            continue
        for stub in case if isinstance(case, list) else [case]:
            if received == stub["query_received"]:
                answer = stub["answer"]
                log_exchange(session_id, query_name, received, stub["query_received"], answer)
                print(answer if plain else json.dumps(answer))
                return 0
    answer = {"error_code": -1, "error_msg": f"no stub data for the query: {received}"}
    log_exchange(session_id, query_name, received, None, answer)
    print(json.dumps(answer))
    return 1
