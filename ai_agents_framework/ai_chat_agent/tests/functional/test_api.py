#!/usr/bin/python

import json
import pytest

from pathlib import Path

from time_utils import get_timestamp
from settings import Settings
from heartbeat import Heartbeat
from utils import get_api_queries
from api_schema_utils import compose_api_queries_pipe_names
from api_fs_query import APIQueryInterruptible

global_settings = Settings()
testdata = list(get_api_queries("/API", global_settings.domain_name_api_entry).items())

def _load_cases(name):
    path = Path(__file__).parent / "api_test_cases" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _arguments(session_id, query):
    values = [f"SESSION_ID={session_id}"]
    values.extend(
        f"{name}={json.dumps(value, ensure_ascii=False)}"
        for name, value in query.items()
    )
    return " ".join(values)


def _wait(api_query, timeout, session_id):
    status, result, _ = api_query.wait_result(
        timeout, session_id, 0.1, max(1, int(timeout / 0.1)), True
    )
    assert status, f"result timed out for session {session_id}"
    return json.loads(result)


def _assert_answer(result, expected, session_id):
    print(f"{get_timestamp()}\tSESSION_ID={session_id}, query result: {result}")
    # Keep the response envelope exact while allowing semantically equivalent
    # wording from the real local language model.
    expected_response = expected.get("response")
    if not isinstance(expected_response, dict):
        assert result == expected, f"unexpected result for SESSION_ID={session_id}"
        return

    assert set(result) == {"response"}, (
        f"unexpected response contract for SESSION_ID={session_id}: {result}"
    )
    assert isinstance(result["response"], str), (
        f"response must be text for SESSION_ID={session_id}: {result}"
    )
    response = result["response"].casefold()
    for fragment in expected_response.get("contains_all", []):
        assert fragment.casefold() in response, (
            f"response for SESSION_ID={session_id} does not contain {fragment!r}: "
            f"{result['response']}"
        )
    alternatives = expected_response.get("contains_any", [])
    if alternatives:
        assert any(fragment.casefold() in response for fragment in alternatives), (
            f"response for SESSION_ID={session_id} contains none of "
            f"{alternatives!r}: {result['response']}"
        )
    for fragment in expected_response.get("excludes", []):
        assert fragment.casefold() not in response, (
            f"response for SESSION_ID={session_id} unexpectedly contains "
            f"{fragment!r}: {result['response']}"
        )


def _check_api(name, query, pipes):
    print(f"{get_timestamp()}\tinitiate test query: {query['Query']}")
    for session_id, test_case in _load_cases(name).items():
        timeout = int(test_case.get("timeout", 900))
        api_query = APIQueryInterruptible(pipes)
        heartbeat = Heartbeat()
        heartbeat.run(f"ai_chat_agent query is in progress; session={session_id}")
        try:
            status, timeout = api_query.execute(
                timeout, _arguments(session_id, test_case["query"])
            )
            assert status, f"query execution timed out for session {session_id}"
            result = _wait(api_query, timeout, session_id)
            _assert_answer(result, test_case["answer"], session_id)
        finally:
            heartbeat.stop()


def check_chat_api(query, pipes):
    _check_api("chat", query, pipes)


@pytest.mark.parametrize("name,query", testdata)
def test_filesystem_api_nodes(name, query):
    print(f"{get_timestamp()}\tExecute test: {name}")
    global global_settings

    # compose expected pipe names, based on query data
    pipes = compose_api_queries_pipe_names(global_settings.api_dir, query)

    if name == "chat":
        check_chat_api(query, pipes)
    else:
        assert 0, f"the query by name: {name} has no test case"
