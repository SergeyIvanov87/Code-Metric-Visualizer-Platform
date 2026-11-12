from concurrent.futures import ThreadPoolExecutor
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time

import pytest

from server import (
    BULK_UPLOAD_TEMPORARY_PREFIX,
    SUPPORTED_SCHEMAS,
    create_app,
    load_schemas,
)


def path(filesystem_api, name):
    return "/" + filesystem_api[1][name]["Query"]


def test_container_packages_schema_utility_dependencies(tmp_path):
    repository = Path(__file__).parents[3]
    service = repository / "ai_agents_framework/ai_agent_http_ambassador"
    dockerfile = (service / "Dockerfile").read_text()
    dockerignore = (service / "Dockerfile.dockerignore").read_text()
    modules = (
        "api_fs_query.py",
        "api_schema_utils.py",
        "api_fs_args.py",
        "filesystem_utils.py",
    )
    for module in modules:
        assert f"common/modules/{module}" in dockerfile
        assert f"!common/modules/{module}" in dockerignore
        shutil.copy2(repository / "common/modules" / module, tmp_path / module)
    shutil.copy2(service / "server.py", tmp_path / "server.py")
    imported = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); import server",
            str(tmp_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert imported.returncode == 0, imported.stderr


def chat_parameter_names(filesystem_api):
    params = filesystem_api[1]["chat"]["Params"]
    message = next(name for name, value in params.items() if value == "")
    system = next(name for name, value in params.items() if value != "")
    return message, system


def chat_payload(filesystem_api, message, system=None):
    message_parameter, system_parameter = chat_parameter_names(filesystem_api)
    payload = {message_parameter: message}
    if system is not None:
        payload[system_parameter] = system
    return payload


def document_parameter(filesystem_api):
    params = filesystem_api[1]["rag_add"]["Params"]
    return next(name for name, value in params.items() if not name.startswith("-") and value == "")


def upload_payload(filesystem_api, content):
    return {
        document_parameter(filesystem_api): base64.b64encode(content).decode("ascii")
    }


def configured_schema_dir(filesystem_api):
    return Path(json.loads(filesystem_api[2].read_text())["schema_dir"])


def test_chat_roundtrip_with_multiline_quotes_unicode_and_shell_characters(app, filesystem_api):
    text = 'Line one\n"Quoted" \\ backslash = equal\nПривет $(touch NEVER) `echo nope`; SESSION_ID=spoof\n'
    system = 'Rules:\n\tKeep "quotes" and a \\ literal\n'
    response = app.test_client().post(
        path(filesystem_api, "chat"),
        json=chat_payload(filesystem_api, text, system),
    )
    assert response.status_code == 200, response.data
    assert response.json["response"] == text.replace("\n", "\r")
    assert response.json["secondary"] == system.replace("\n", "\r")


def test_concurrent_large_prompts_do_not_mix_sessions(app, filesystem_api):
    texts = [f"Request {index}: " + ("🙂 long input " * 400) for index in range(4)]

    def send(text):
        return app.test_client().post(
            path(filesystem_api, "chat"),
            json=chat_payload(filesystem_api, text, "Ground answers"),
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(send, texts))
    for text, response in zip(texts, results):
        assert response.status_code == 200, response.data
        assert response.json["response"] == text


def test_schema_driven_pages_load(app, filesystem_api):
    client = app.test_client()
    page = client.get(path(filesystem_api, "chat") + "/")
    assert page.status_code == 200
    main_menu_link = b'<a href="/api.pmccabe_collector.restapi.org">Return to the main menu</a>'
    help_link = b'<a href="/help">Ambassador help</a>'
    upload_link = f'<a href="{path(filesystem_api, "rag_add")}">Add a document to the knowledge base</a>'.encode()
    assert page.data.index(main_menu_link) < page.data.index(help_link)
    assert page.data.index(help_link) < page.data.index(upload_link)
    assert b"You are a knowledge-base assistant." in page.data
    assert b"const requestParameters =" in page.data
    for parameter in filesystem_api[1]["chat"]["Params"]:
        assert parameter.encode() in page.data
    assert b"<details>" in page.data and b"<details open" not in page.data
    assert b'<input id="include-history" type="checkbox" checked>' in page.data
    assert b"/ai-agent-ui/" not in page.data

    upload_page = client.get(path(filesystem_api, "rag_add"))
    assert upload_page.status_code == 200
    chat_link = f'<a href="{path(filesystem_api, "chat")}">Chat with the knowledge base</a>'.encode()
    assert upload_page.data.index(main_menu_link) < upload_page.data.index(chat_link)
    assert document_parameter(filesystem_api).encode() in upload_page.data
    assert b"application/json" in upload_page.data

    help_page = client.get("/help/")
    assert help_page.status_code == 200
    assert b"<h2>RAG bulk-add flow</h2>" in help_page.data
    assert b"The central idea is that the ambassador" in help_page.data
    assert client.get("/healthz").json == {"ready": True}


def test_main_menu_path_comes_from_environment(filesystem_api, monkeypatch):
    monkeypatch.setenv("MAIN_MENU_PATH", "/custom/main-menu")
    app = create_app(filesystem_api[2])
    page = app.test_client().get(path(filesystem_api, "chat"))
    assert page.status_code == 200
    assert b'<a href="/custom/main-menu">Return to the main menu</a>' in page.data


def test_discovery_endpoint_lists_schema_paths(app, filesystem_api):
    response = app.test_client().get("/.well-known/http-api-routes/v1")
    assert response.status_code == 200
    assert response.json["schema_version"] == 1
    assert response.json["revision"].startswith("sha256:")
    expected = [
        {
            "path": "/" + schema["Query"],
            "timeout_seconds": 40,
        }
        for schema in filesystem_api[1].values()
    ]
    expected.append({"path": "/help", "timeout_seconds": 40})
    assert response.json["routes"] == sorted(
        expected, key=lambda route: route["path"]
    )


def test_loads_every_configured_supported_schema(app, filesystem_api):
    assert set(load_schemas(configured_schema_dir(filesystem_api))) == set(SUPPORTED_SCHEMAS)


def test_ignores_json_file_without_query(filesystem_api):
    schema_dir = configured_schema_dir(filesystem_api)
    (schema_dir / "metadata.json").write_text(json.dumps({"description": "not a query"}))
    assert create_app(filesystem_api[2]) is not None


def test_rejects_query_not_supported_by_server(filesystem_api):
    schema_dir = configured_schema_dir(filesystem_api)
    unsupported_query = "api.pmccabe_collector.restapi.org/ai_agent/rag/sync/v1"
    (schema_dir / "rag_sync.json").write_text(json.dumps({
        "Content-Type": "application/json",
        "Method": "PUT",
        "Query": unsupported_query,
        "Params": {},
    }))
    with pytest.raises(ValueError, match=unsupported_query):
        create_app(filesystem_api[2])


def test_upload_passes_inline_document_parameter_to_filesystem_api(app, filesystem_api):
    document = "A UTF-8 document.\nSecond line: 日本語\n".encode()
    response = app.test_client().put(
        path(filesystem_api, "rag_add"),
        json=upload_payload(filesystem_api, document),
    )
    assert response.status_code == 200, response.data
    assert response.json["document"] == document.decode()
    assert response.json["doc_type"] == "txt"
    assert response.json["doc_id"] == "fixture-document"
    assert not (filesystem_api[0] / ".http_ambassador").exists()


@pytest.mark.parametrize("payload", [None, [], "invalid"], ids=["null", "array", "string"])
def test_actions_require_json_parameter_object(app, filesystem_api, payload):
    response = app.test_client().post(path(filesystem_api, "chat"), json=payload)
    assert response.status_code == 400


def test_http_parameters_are_forwarded_without_name_mapping(filesystem_api):
    class RecordingQuery:
        commands = []

        def __init__(self, pipes, remove_session_pipe_on_result_done=False):
            self.pipes = pipes

        def is_valid(self):
            return True

        def execute(self, timeout, command):
            self.commands.append(command)
            return True, timeout

        def wait_result(self, timeout, session_id, *args):
            return True, '{"response":"ok"}', timeout

    app = create_app(filesystem_api[2], RecordingQuery)
    payload = {"arbitrary_parameter": "kept as received"}
    response = app.test_client().post(path(filesystem_api, "chat"), json=payload)
    assert response.status_code == 200
    assert 'arbitrary_parameter="kept as received"' in RecordingQuery.commands[-1]


def test_unavailable_api_returns_503(app, filesystem_api):
    schema = filesystem_api[1]["chat"]
    (filesystem_api[0] / schema["Query"] / schema["Method"] / "result.json").unlink()
    response = app.test_client().post(
        path(filesystem_api, "chat"),
        json=chat_payload(filesystem_api, "Hello"),
    )
    assert response.status_code == 503
    assert app.test_client().get("/healthz").status_code == 503


def test_interruptible_write_timeout_returns_504(filesystem_api):
    class TimedOutQuery:
        def __init__(self, pipes, remove_session_pipe_on_result_done=False):
            pass

        def is_valid(self):
            return True

        def execute(self, timeout, command):
            return False, 0

    app = create_app(filesystem_api[2], TimedOutQuery)
    response = app.test_client().post(
        path(filesystem_api, "chat"),
        json=chat_payload(filesystem_api, "Hello"),
    )
    assert response.status_code == 504
    assert response.json["completion_unknown"] is True


@pytest.mark.parametrize("raw", ["not JSON", "[]"])
def test_invalid_filesystem_results_return_502(filesystem_api, raw):
    class ResultQuery:
        def __init__(self, pipes, remove_session_pipe_on_result_done=False):
            pass

        def is_valid(self):
            return True

        def execute(self, timeout, command):
            return True, timeout

        def wait_result(self, timeout, session_id, *args):
            return True, raw, timeout

    app = create_app(filesystem_api[2], ResultQuery)
    response = app.test_client().post(
        path(filesystem_api, "chat"),
        json=chat_payload(filesystem_api, "Hello"),
    )
    assert response.status_code == 502


def test_completed_sessions_are_reused(app, filesystem_api):
    url = path(filesystem_api, "chat")
    client = app.test_client()
    assert client.post(url, json=chat_payload(filesystem_api, "First")).status_code == 200
    assert client.post(url, json=chat_payload(filesystem_api, "Second")).status_code == 200
    schema = filesystem_api[1]["chat"]
    node = filesystem_api[0] / schema["Query"] / schema["Method"]
    assert len(list(node.glob("result.json_http_*"))) == 1


def test_interruptible_result_wait_has_bounded_deadline(
    tmp_path, filesystem_api
):
    schema = filesystem_api[1]["chat"]
    node = tmp_path / schema["Query"] / schema["Method"]
    node.mkdir(parents=True)
    for name in ("exec", "result.json"):
        os.mkfifo(node / name)

    config = json.loads(filesystem_api[2].read_text())
    config["api_mount"] = str(tmp_path)
    config["timeout_seconds"] = 0.1
    config_path = tmp_path / "timeout.json"
    config_path.write_text(json.dumps(config))

    def stalled_agent():
        with (node / "exec").open() as input_pipe:
            command = input_pipe.read()
        assert re.search(r"SESSION_ID=\"http_[a-f0-9]+\"", command)

    thread = threading.Thread(target=stalled_agent, daemon=True)
    thread.start()
    started = time.monotonic()
    try:
        app = create_app(config_path)
        response = app.test_client().post(
            "/" + schema["Query"],
            json=chat_payload(filesystem_api, "Hello"),
        )
        assert response.status_code == 504
        assert time.monotonic() - started < 1
    finally:
        thread.join(timeout=1)
    assert not thread.is_alive()


def test_oversized_result_returns_502(filesystem_api):
    config = json.loads(filesystem_api[2].read_text())
    config["max_result_bytes"] = 10
    filesystem_api[2].write_text(json.dumps(config))
    app = create_app(filesystem_api[2])
    response = app.test_client().post(
        path(filesystem_api, "chat"),
        json=chat_payload(filesystem_api, "A large reply"),
    )
    assert response.status_code == 502


def test_nul_argument_is_rejected_before_fifo_write(app, filesystem_api):
    response = app.test_client().post(
        path(filesystem_api, "chat"),
        json=chat_payload(filesystem_api, "\0"),
    )
    assert response.status_code == 400


def test_unsupported_action_method_returns_405(app, filesystem_api):
    response = app.test_client().put(
        path(filesystem_api, "chat"),
        json=chat_payload(filesystem_api, "Hello"),
    )
    assert response.status_code == 405


def bulk_schema_name():
    return next(
        name
        for name, support in SUPPORTED_SCHEMAS.items()
        if support.get("bulk_upload")
    )


def bulk_session(filesystem_api):
    schema = filesystem_api[1][bulk_schema_name()]
    request_directory = (
        filesystem_api[0] / schema["Query"] / schema["Method"]
        / "deferred-test-session"
    )
    input_directory = request_directory / "input"
    uploader_request = filesystem_api[0] / "uploader-request"
    input_directory.mkdir(parents=True)
    uploader_request.mkdir()
    for fifo in (
        request_directory / "events",
        request_directory / "async_result",
        uploader_request / "seal",
    ):
        os.mkfifo(fifo)
    (request_directory / "stage.json").write_text(json.dumps({
        "uploader_request": str(uploader_request),
    }))
    report = {
        "input": str(input_directory),
        "events": str(request_directory / "events"),
        "result": str(request_directory / "async_result"),
        "protocol": "cmvp.rag-bulk-events.v1",
    }
    return schema, request_directory, uploader_request, report


def test_bulk_page_has_multi_file_folder_and_collapsed_schema_settings(
    app, filesystem_api
):
    schema_name = bulk_schema_name()
    response = app.test_client().get(path(filesystem_api, schema_name))
    assert response.status_code == 200
    assert b'type="file" multiple' in response.data
    assert b"Choose folders" in response.data
    folder_picker = response.data.split(b'id="bulk-folders"', 1)[1].split(b">", 1)[0]
    for attribute in (b"directory", b"mozdirectory", b"webkitdirectory", b"multiple"):
        assert attribute in folder_picker
    assert b"reopen it to add more" in response.data
    assert b"<details>" in response.data
    assert b"<details open" not in response.data
    visible_parameters = {
        name: default
        for name, default in filesystem_api[1][schema_name]["Params"].items()
        if name not in ("SESSION_ID", "preserveOriginal")
    }
    visible_parameters.update(
        SUPPORTED_SCHEMAS[schema_name].get("page_parameter_defaults", {})
    )
    for name, default in visible_parameters.items():
        assert f'data-parameter="{name}"'.encode() in response.data
        assert f'value="{default}"'.encode() in response.data
    assert b"Promise.all" in response.data
    assert b"error.payload = result" in response.data
    assert b"result.result.failed" in response.data
    assert b"finished.result.statistics" in response.data
    assert b"statistics.failed" in response.data


def test_bulk_upload_starts_query_forwards_settings_and_publishes_files_in_parallel(
    filesystem_api, monkeypatch
):
    schema, request_directory, _uploader_request, report = bulk_session(filesystem_api)

    class BulkQuery:
        commands = []

        def __init__(self, pipes, remove_session_pipe_on_result_done=False):
            self.pipes = pipes

        def is_valid(self):
            return True

        def execute(self, timeout, command):
            self.commands.append(command)
            return True, timeout

        def wait_result(self, timeout, session_id, *args):
            return True, json.dumps(report), timeout

    app = create_app(filesystem_api[2], BulkQuery)
    url = "/" + schema["Query"]
    settings = {
        name: default for name, default in schema["Params"].items()
        if name not in ("SESSION_ID", "preserveOriginal")
    }
    settings[next(name for name in settings if name.startswith("-"))] = "team=docs"
    settings["WaitQueryUpdateTimeoutSec"] = "1"
    settings["dir_skip_regex"] = "(?!)"
    started = app.test_client().post(url, json=settings)
    assert started.status_code == 200
    assert started.json["upload_id"] == request_directory.name
    for name, value in settings.items():
        assert f'{name}="{value}"' in BulkQuery.commands[-1]
    assert 'WaitQueryUpdateTimeoutSec="1"' in BulkQuery.commands[-1]

    uploads = {
        "one.txt": b"first",
        "folder/two.txt": b"second",
        "folder/deeper/three.md": b"third",
    }
    stage = (request_directory / "input").resolve()
    incoming = stage.parent / (
        f"{BULK_UPLOAD_TEMPORARY_PREFIX}{request_directory.name}"
    )
    linked_sources = []
    real_link = os.link

    def checked_link(source, destination):
        source = Path(source)
        assert source.parent == incoming
        assert not source.is_relative_to(stage)
        linked_sources.append(source)
        return real_link(source, destination)

    monkeypatch.setattr(os, "link", checked_link)

    def upload(item):
        relative, content = item
        return app.test_client().put(
            url,
            query_string={
                "upload_id": request_directory.name,
                "path": relative,
            },
            data=content,
            content_type="application/octet-stream",
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(upload, uploads.items()))
    assert all(response.status_code == 200 for response in responses)
    for relative, content in uploads.items():
        assert (request_directory / "input" / relative).read_bytes() == content
    assert len(linked_sources) == len(uploads)
    assert not (stage / ".incoming").exists()
    assert incoming.is_dir()
    assert not any(incoming.iterdir())


def test_bulk_upload_rejects_path_traversal(filesystem_api):
    schema, request_directory, _uploader_request, report = bulk_session(filesystem_api)

    class BulkQuery:
        def __init__(self, pipes, remove_session_pipe_on_result_done=False):
            pass

        def is_valid(self):
            return True

        def execute(self, timeout, command):
            return True, timeout

        def wait_result(self, timeout, session_id, *args):
            return True, json.dumps(report), timeout

    app = create_app(filesystem_api[2], BulkQuery)
    response = app.test_client().put(
        "/" + schema["Query"],
        query_string={"upload_id": request_directory.name, "path": "../escape"},
        data=b"nope",
        content_type="application/octet-stream",
    )
    assert response.status_code == 400
    assert not (request_directory.parent / "escape").exists()


def test_bulk_finish_returns_partial_failures_as_successful_statistics(filesystem_api):
    schema, request_directory, uploader_request, report = bulk_session(filesystem_api)

    class BulkQuery:
        def __init__(self, pipes, remove_session_pipe_on_result_done=False):
            pass

        def is_valid(self):
            return True

        def execute(self, timeout, command):
            return True, timeout

        def wait_result(self, timeout, session_id, *args):
            return True, json.dumps(report), timeout

    expected_result = {
        "error_code": "0",
        "statistics": {"total": 2, "added": 1, "failed": 1},
        "added": [{"path": "folder/file.txt", "status": "added"}],
        "failed": [{
            "path": "folder/image.png",
            "status": "failed",
            "doc_type": "image,png",
            "rag_result": {
                "error_code": -1,
                "error_msg": 'The "image" document category is unsupported',
            },
        }],
    }

    def represented_service():
        with (uploader_request / "seal").open("rb", buffering=0) as seal:
            assert seal.read()
        with (request_directory / "events").open("wb", buffering=0) as events:
            events.write(
                json.dumps({"path": "folder/file.txt", "status": "added"}).encode()
                + b"\n"
            )
            events.write(
                json.dumps({"status": "terminated"}).encode() + b"\n"
            )
        with (request_directory / "async_result").open("wb", buffering=0) as result:
            result.write(json.dumps(expected_result).encode())

    backend = threading.Thread(target=represented_service)
    backend.start()
    app = create_app(filesystem_api[2], BulkQuery)
    stage = (request_directory / "input").resolve()
    incoming = stage.parent / (
        f"{BULK_UPLOAD_TEMPORARY_PREFIX}{request_directory.name}"
    )
    incoming.mkdir()
    response = app.test_client().patch(
        "/" + schema["Query"],
        query_string={"upload_id": request_directory.name},
    )
    backend.join(timeout=2)
    assert not backend.is_alive()
    assert response.status_code == 200, response.data
    assert response.json["result"] == expected_result
    assert response.json["events"][-1]["status"] == "terminated"
    assert not incoming.exists()
