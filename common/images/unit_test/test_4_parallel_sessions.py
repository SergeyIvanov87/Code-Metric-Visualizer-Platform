#!/usr/bin/python

"""Regression tests for opt-in request parallelism grouped by SESSION_ID."""

import json
import os
import shlex
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from api_fs_query import APIQueryInterruptible
from api_schema_utils import compose_api_queries_pipe_names
from build_api_services import create_cli_server_content_from_schema
from settings import Settings


SETTINGS = Settings()
API_SCHEMA_DIRECTORY = Path("/API")


def _load_schema(request_name):
    return json.loads((API_SCHEMA_DIRECTORY / f"{request_name}.json").read_text())


def _query_for(request_name):
    schema = _load_schema(request_name)
    query = APIQueryInterruptible(
        compose_api_queries_pipe_names(SETTINGS.api_dir, schema),
        remove_session_pipe_on_result_done=False,
    )
    assert query.wait_until_valid(0.02, 250, True)
    return query


def _install_request_command(body):
    command = Path(SETTINGS.work_dir) / "generated" / "req_cmd.sh"
    command.write_text("#!/usr/bin/env bash\nset -u\n" + body)
    command.chmod(0o755)


def _execute(query, session_id, tag, timeout=4):
    status, _ = query.execute(
        timeout,
        f"SESSION_ID={session_id} param_1={tag}",
    )
    assert status, f"request for session {session_id!r} was not accepted"


def _wait_result(query, session_id, timeout=8):
    status, result, _ = query.wait_result(
        timeout,
        session_id,
        0.02,
        int(timeout / 0.02) + 1,
        True,
    )
    assert status, f"request for session {session_id!r} produced no result"
    return result


def _wait_until(predicate, timeout=4, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _line_count(path):
    if not path.exists():
        return 0
    return len(path.read_text().splitlines())


def test_parallel_by_session_is_opt_in(run_around_tests):
    services = Path(SETTINGS.work_dir) / "generated" / "services"
    parallel_server = (services / "req_1_server.sh").read_text()
    legacy_server = (services / "req_2_server.sh").read_text()

    assert "parallel_session_request()" in parallel_server
    assert "declare -A PARALLEL_REQUEST_STATE" in parallel_server
    assert 'exec {PARALLEL_REQUEST_READ_FD}<"${pipe_request}"' in parallel_server
    assert (
        'exec {PARALLEL_REQUEST_KEEPALIVE_FD}>"${pipe_request}"'
        in parallel_server
    )
    assert (
        'read -r -u "${PARALLEL_REQUEST_READ_FD}" CMD_READ'
        in parallel_server
    )
    assert "cat $pipe_request" not in parallel_server
    assert "exec {PARALLEL_REQUEST_KEEPALIVE_FD}>&-" in parallel_server
    assert "exec {PARALLEL_REQUEST_READ_FD}<&-" in parallel_server
    assert "parallel_session_request()" not in legacy_server
    assert "declare -A PARALLEL_REQUEST_STATE" not in legacy_server
    assert "cat $pipe_request" in legacy_server


def test_parallel_by_session_requires_a_boolean(run_around_tests):
    schema = _load_schema("req_1")
    schema["ParallelBySession"] = "true"

    with pytest.raises(ValueError, match="ParallelBySession must be a boolean"):
        create_cli_server_content_from_schema("req_1", schema, "/tmp/generated")


def test_different_sessions_execute_concurrently_and_route_results(
    run_around_tests, tmp_path
):
    state = tmp_path / "different-sessions"
    state.mkdir()
    quoted_state = shlex.quote(os.fspath(state))
    _install_request_command(
        f"""state={quoted_state}
: > "${{state}}/started.${{BASHPID}}"
while [[ ! -e "${{state}}/release" ]]; do
    sleep 0.02
done
"""
    )
    query = _query_for("req_1")

    overlapped = False
    try:
        _execute(query, "parallel-alpha", "alpha")
        _execute(query, "parallel-beta", "beta")
        overlapped = _wait_until(
            lambda: len(list(state.glob("started.*"))) == 2,
            timeout=3,
        )
    finally:
        (state / "release").touch()

    assert overlapped, "executors for different sessions did not overlap"
    alpha_result = _wait_result(query, "parallel-alpha")
    beta_result = _wait_result(query, "parallel-beta")
    assert "alpha" in alpha_result
    assert "beta" not in alpha_result
    assert "beta" in beta_result
    assert "alpha" not in beta_result


def test_parallel_request_fifo_accepts_concurrent_bursts_after_idle_gaps(
    run_around_tests,
):
    _install_request_command("true\n")
    query = _query_for("req_1")

    def execute_burst(prefix, count):
        requests = [
            (f"persistent-reader-{prefix}-{index}", f"{prefix}-{index}")
            for index in range(count)
        ]
        with ThreadPoolExecutor(max_workers=count) as executor:
            futures = [
                executor.submit(_execute, query, session_id, tag)
                for session_id, tag in requests
            ]
            for future in futures:
                future.result()
        for session_id, tag in requests:
            result = _wait_result(query, session_id)
            assert tag in result

    execute_burst("first", 24)
    time.sleep(0.25)
    execute_burst("second", 24)


def test_same_session_waits_for_the_previous_executor(run_around_tests, tmp_path):
    state = tmp_path / "same-session"
    state.mkdir()
    quoted_state = shlex.quote(os.fspath(state))
    _install_request_command(
        f"""state={quoted_state}
if mkdir "${{state}}/first.claim" 2>/dev/null; then
    : > "${{state}}/first-started"
    while [[ ! -e "${{state}}/release" ]]; do
        sleep 0.02
    done
else
    : > "${{state}}/second-started"
fi
"""
    )
    query = _query_for("req_1")
    session_id = "serialized-session"

    _execute(query, session_id, "first")
    assert _wait_until((state / "first-started").exists)
    _execute(query, session_id, "second")

    second_started_early = _wait_until(
        (state / "second-started").exists,
        timeout=0.75,
    )
    (state / "release").touch()

    assert not second_started_early, "same-session executors overlapped"
    assert _wait_until((state / "second-started").exists)
    result = _wait_result(query, session_id)
    assert "second" in result
    assert "first" not in result


def test_new_same_session_request_drains_each_unread_predecessor(
    run_around_tests, tmp_path
):
    state = tmp_path / "stale-results"
    state.mkdir()
    invocations = state / "invocations"
    _install_request_command(
        "printf '%s\\n' \"${BASHPID}\" >> "
        + shlex.quote(os.fspath(invocations))
        + "\n"
    )
    query = _query_for("req_1")
    session_id = "stale-result-session"

    _execute(query, session_id, "discard-one")
    assert _wait_until(lambda: _line_count(invocations) == 1)

    # Nobody reads the first result. The second request must drain it before
    # entering the executor, then block publishing its own unread result.
    _execute(query, session_id, "discard-two")
    assert _wait_until(lambda: _line_count(invocations) == 2)

    # Repeat the transition to verify that state is advanced request by
    # request rather than only handling the first stale writer.
    _execute(query, session_id, "keep-three")
    assert _wait_until(lambda: _line_count(invocations) == 3)

    result = _wait_result(query, session_id)
    assert "keep-three" in result
    assert "discard-one" not in result
    assert "discard-two" not in result


def test_endpoint_without_opt_in_keeps_legacy_serial_execution(
    run_around_tests, tmp_path
):
    state = tmp_path / "legacy-serial"
    state.mkdir()
    quoted_state = shlex.quote(os.fspath(state))
    _install_request_command(
        f"""state={quoted_state}
if mkdir "${{state}}/first.claim" 2>/dev/null; then
    : > "${{state}}/first-started"
    while [[ ! -e "${{state}}/release" ]]; do
        sleep 0.02
    done
else
    : > "${{state}}/second-started"
fi
"""
    )
    query = _query_for("req_2")

    _execute(query, "legacy-alpha", "first")
    assert _wait_until((state / "first-started").exists)
    try:
        accepted, _ = query.execute(
            1,
            "SESSION_ID=legacy-beta param_1=second",
        )
    finally:
        (state / "release").touch()

    assert not accepted, "a legacy serial server accepted a concurrent request"
    assert not (state / "second-started").exists()
    result = _wait_result(query, "legacy-alpha")
    assert "first" in result
