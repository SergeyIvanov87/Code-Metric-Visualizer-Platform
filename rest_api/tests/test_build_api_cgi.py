#!/usr/bin/python

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace


TEST_DIRECTORY = Path(__file__).resolve().parent

# In repo layout tests/ is under <repo>/rest_api/tests, so parents[1] is repo root.
# In the functional-test Docker image the tests are copied into /tests and
# do not have two parents; handle that gracefully.
try:
    REPOSITORY_ROOT = TEST_DIRECTORY.parents[1]
except IndexError:
    REPOSITORY_ROOT = TEST_DIRECTORY

if (REPOSITORY_ROOT / "rest_api" / "build_api_cgi.py").is_file():
    BUILD_API_CGI = REPOSITORY_ROOT / "rest_api" / "build_api_cgi.py"
    COMMON_DIRECTORY = REPOSITORY_ROOT / "common"
else:
    # The REST API functional-test image copies this test and the generator
    # into /tests, while common helpers are inherited under /tests/utils.
    BUILD_API_CGI = TEST_DIRECTORY / "build_api_cgi.py"
    COMMON_DIRECTORY = TEST_DIRECTORY / "utils"


def generate_cgi(tmp_path):
    schema_directory = tmp_path / "schemas"
    schema_directory.mkdir()
    (schema_directory / "probe.json").write_text(
        json.dumps(
            {
                "Content-Type": "text/plain",
                "Method": "GET",
                "Query": "api.pmccabe_collector.restapi.org/probe",
                "Params": {},
            }
        )
    )

    environment = os.environ.copy()
    python_path = [
        str(COMMON_DIRECTORY),
        str(COMMON_DIRECTORY / "modules"),
    ]
    if environment.get("PYTHONPATH"):
        python_path.append(environment["PYTHONPATH"])
    environment["PYTHONPATH"] = os.pathsep.join(python_path)

    result = subprocess.run(
        [
            sys.executable,
            str(BUILD_API_CGI),
            str(schema_directory),
            "/api",
            "api.pmccabe_collector.restapi.org",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return result.stdout


class FakeApplication:
    def route(self, *_args, **_kwargs):
        return lambda handler: handler


class FakeLogger:
    def debug(self, *_args, **_kwargs):
        pass

    def error(self, *_args, **_kwargs):
        pass


def load_generated_handler(generated_cgi, async_query_type):
    namespace = {
        "app": FakeApplication(),
        "redirect": lambda path: path,
        "render_template": lambda *_args, **_kwargs: "",
        "request": SimpleNamespace(
            method="HEAD",
            full_path="/api.pmccabe_collector.restapi.org/probe",
            remote_addr="127.0.0.1",
        ),
        "socket": SimpleNamespace(
            gethostname=lambda: "rest-api",
            gethostbyaddr=lambda _address: ("client", [], []),
        ),
        "time": SimpleNamespace(time=lambda: 123.456),
        "APIQuery": async_query_type,
        "APIQueryInterruptible": async_query_type,
        "docker_logger": FakeLogger(),
        "queries_in_progress": 0,
    }
    exec(compile(generated_cgi, "<generated-cgi>", "exec"), namespace)
    handler = next(
        value
        for name, value in namespace.items()
        if name.endswith("_probe") and callable(value)
    )
    return namespace, handler


def test_head_probe_is_tracked_for_its_complete_transaction(tmp_path):
    generated_cgi = generate_cgi(tmp_path)
    syntax_tree = ast.parse(generated_cgi)
    handler = next(
        node
        for node in syntax_tree.body
        if isinstance(node, ast.FunctionDef) and node.name.endswith("_probe")
    )
    head_handler = next(
        node
        for node in handler.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and any(
            isinstance(comparator, ast.Constant) and comparator.value == "HEAD"
            for comparator in node.test.comparators
        )
    )

    increment, protected_transaction = head_handler.body
    assert isinstance(increment, ast.AugAssign)
    assert isinstance(increment.target, ast.Name)
    assert increment.target.id == "queries_in_progress"
    assert isinstance(increment.op, ast.Add)
    assert isinstance(increment.value, ast.Constant)
    assert increment.value.value == 1

    assert isinstance(protected_transaction, ast.Try)
    assert len(protected_transaction.finalbody) == 1
    decrement = protected_transaction.finalbody[0]
    assert isinstance(decrement, ast.AugAssign)
    assert isinstance(decrement.target, ast.Name)
    assert decrement.target.id == "queries_in_progress"
    assert isinstance(decrement.op, ast.Sub)
    assert isinstance(decrement.value, ast.Constant)
    assert decrement.value.value == 1

    calls = [
        node
        for node in ast.walk(protected_transaction)
        if isinstance(node, ast.Call)
    ]
    called_methods = {
        node.func.attr
        for node in calls
        if isinstance(node.func, ast.Attribute)
    }
    assert {"execute", "wait_result"} <= called_methods


def test_head_probe_stays_active_until_its_result_is_consumed(tmp_path):
    generated_cgi = generate_cgi(tmp_path)
    state = {}

    class SuccessfulQuery:
        def __init__(self, *_args, **_kwargs):
            self.keep_alive_tag = None

        def is_valid(self):
            return True

        def execute(self, timeout, query):
            assert state["namespace"]["queries_in_progress"] == 1
            self.keep_alive_tag = query.split("API_KEEP_ALIVE_CHECK=", 1)[1].split(
                " ", 1
            )[0]
            return True, timeout

        def wait_result(self, timeout, *_args):
            assert state["namespace"]["queries_in_progress"] == 1
            return True, self.keep_alive_tag, timeout

    namespace, handler = load_generated_handler(generated_cgi, SuccessfulQuery)
    state["namespace"] = namespace

    assert handler() == ("", 200)
    assert namespace["queries_in_progress"] == 0


def test_head_probe_releases_active_count_when_result_wait_fails(tmp_path):
    generated_cgi = generate_cgi(tmp_path)
    state = {}

    class FailingQuery:
        def __init__(self, *_args, **_kwargs):
            pass

        def is_valid(self):
            return True

        def execute(self, timeout, _query):
            assert state["namespace"]["queries_in_progress"] == 1
            return True, timeout

        def wait_result(self, _timeout, *_args):
            assert state["namespace"]["queries_in_progress"] == 1
            raise RuntimeError("result wait failed")

    namespace, handler = load_generated_handler(generated_cgi, FailingQuery)
    state["namespace"] = namespace

    try:
        handler()
    except RuntimeError as error:
        assert str(error) == "result wait failed"
    else:
        raise AssertionError("HEAD result failure must propagate")

    assert namespace["queries_in_progress"] == 0
