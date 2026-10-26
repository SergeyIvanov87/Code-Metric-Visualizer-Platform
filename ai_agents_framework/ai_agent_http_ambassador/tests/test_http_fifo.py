from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import threading
import time

import pytest

from fifo_client import FifoClient, InvalidResult, QueryTimeout, Unavailable
from server import create_app


def path(filesystem_api, name):
    return "/" + filesystem_api[1][name]["Query"]


def test_chat_roundtrip_with_multiline_quotes_unicode_and_shell_characters(app, filesystem_api):
    text = 'Line one\n"Quoted" \\ backslash = equal\nПривет $(touch NEVER) `echo nope`; SESSION_ID=spoof\n'
    system = 'Rules:\n\tKeep "quotes" and a \\ literal\n'
    response = app.test_client().post(path(filesystem_api, "chat"), json={"user_prompt": text, "system_prompt": system})
    assert response.status_code == 200, response.data
    assert response.json["response"] == text.replace("\n", "\r")
    assert response.json["system_prompt"] == system.replace("\n", "\r")


def test_concurrent_large_prompts_do_not_mix_sessions(app, filesystem_api):
    # Each command exceeds Linux PIPE_BUF (4096 bytes), exercising partial writes.
    texts = [f"Request {index}: " + ("🙂 long input " * 400) for index in range(4)]
    def send(text):
        return app.test_client().post(path(filesystem_api, "chat"), json={"user_prompt": text, "system_prompt": "Ground answers"})
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(send, texts))
    for text, response in zip(texts, results):
        assert response.status_code == 200, response.data
        assert response.json["response"] == text


def test_default_prompt_comes_from_schema_and_pages_load(app, filesystem_api):
    client = app.test_client()
    page = client.get(path(filesystem_api, "chat") + "/")
    assert page.status_code == 200
    main_menu_link = b'<a href="/api.pmccabe_collector.restapi.org">Return to the main menu</a>'
    upload_link = f'<a href="{path(filesystem_api, "rag_add")}">Add a document to the knowledge base</a>'.encode()
    assert page.data.index(main_menu_link) < page.data.index(upload_link)
    assert b"You are a knowledge-base assistant." in page.data
    assert b"<details>" in page.data and b"<details open" not in page.data
    assert b'<input id="include-history" type="checkbox" checked>' in page.data
    assert b"Include chat history with this message" in page.data
    assert b"/ai-agent-ui/" not in page.data
    assert b'fetch(window.location.pathname' in page.data
    assert b"const prompt = includeHistory.checked" in page.data
    assert b": text;" in page.data
    chat_script = page.data.index(b"<script nonce=")
    assert page.data.index(b'<form id="chat-form">') < chat_script
    assert b"defer" not in page.data[chat_script:page.data.index(b">", chat_script)]
    assert "Content-Security-Policy" in page.headers
    assert client.get("/ai-agent-ui/static/chat.js").status_code == 404
    upload_page = client.get(path(filesystem_api, "rag_add"))
    assert upload_page.status_code == 200
    chat_link = f'<a href="{path(filesystem_api, "chat")}">Chat with the knowledge base</a>'.encode()
    assert upload_page.data.index(main_menu_link) < upload_page.data.index(chat_link)
    upload_script = upload_page.data.index(b"<script nonce=")
    assert upload_page.data.index(b'<input id="file"') < upload_script
    assert b"defer" not in upload_page.data[
        upload_script:upload_page.data.index(b">", upload_script)
    ]
    response = client.post(path(filesystem_api, "chat"), json={"user_prompt": "Hello"})
    assert response.status_code == 200
    assert response.json["system_prompt"].startswith("You are a knowledge-base assistant.")
    assert not response.json["system_prompt"].startswith('"')
    assert client.get("/healthz").json == {"ready": True}


def test_discovery_endpoint_lists_ambassador_paths(app, filesystem_api):
    response = app.test_client().get("/.well-known/http-api-routes/v1")
    assert response.status_code == 200
    assert response.json["schema_version"] == 1
    assert response.json["revision"].startswith("sha256:")
    assert response.json["routes"] == sorted(
        [
            {
                "path": path(filesystem_api, name),
                "timeout_seconds": 40,
            }
            for name in ("chat", "rag_add")
        ],
        key=lambda route: route["path"],
    )


def test_upload_stages_file_for_agent_and_cleans_it_after_result(app, filesystem_api):
    document = "A UTF-8 document.\nSecond line: 日本語\n"
    response = app.test_client().put(path(filesystem_api, "rag_add"), data=document.encode(), content_type="application/octet-stream", headers={"X-Filename": "../../$(touch NEVER).pdf"})
    assert response.status_code == 200, response.data
    assert response.json["document"] == document
    assert response.json["doc_type"] == "txt"
    assert response.json["doc_id"] == "fixture-document"
    assert ".http_ambassador/staging/" in response.json["uri"]
    assert not os.path.exists(response.json["uri"])
    assert not list((filesystem_api[0] / ".http_ambassador/staging").iterdir())


@pytest.mark.parametrize("data,content_type,status", [(b"", "application/octet-stream", 400), (b"\xff\xfe", "application/octet-stream", 415), (b"text", "text/plain", 415), (b"x" * (1024 * 1024 + 1), "application/octet-stream", 413)], ids=["empty", "binary", "wrong-media-type", "oversized"])
def test_reject_invalid_upload(app, filesystem_api, data, content_type, status):
    response = app.test_client().put(path(filesystem_api, "rag_add"), data=data, content_type=content_type)
    assert response.status_code == status


@pytest.mark.parametrize("data,status", [({}, 400), ({"user_prompt": " "}, 400), ({"user_prompt": "\0"}, 400), ({"user_prompt": 1}, 400), ({"user_prompt": "hello", "-URI": "/etc/passwd"}, 400), ({"user_prompt": "x" * 65537}, 413)], ids=["missing", "blank", "nul", "number", "extra-argument", "oversized"])
def test_reject_invalid_prompts(app, filesystem_api, data, status):
    response = app.test_client().post(path(filesystem_api, "chat"), json=data)
    assert response.status_code == status


def test_unavailable_api_returns_503(app, filesystem_api):
    schema = filesystem_api[1]["chat"]
    (filesystem_api[0] / schema["Query"] / "POST/result.json").unlink()
    response = app.test_client().post(path(filesystem_api, "chat"), json={"user_prompt": "Hello"})
    assert response.status_code == 503
    assert app.test_client().get("/healthz").status_code == 503


def test_stalled_exec_fifo_has_bounded_timeout(tmp_path, filesystem_api):
    schema = filesystem_api[1]["chat"]
    node = tmp_path / schema["Query"] / "POST"
    node.mkdir(parents=True)
    for name in ("exec", "result.json"):
        os.mkfifo(node / name)
    start = time.monotonic()
    with pytest.raises(QueryTimeout):
        FifoClient(tmp_path, timeout_seconds=0.1).execute(schema, {"-user_prompt": "Hello"})
    assert time.monotonic() - start < 1


def test_regular_file_cannot_replace_exec_fifo(tmp_path, filesystem_api):
    schema = filesystem_api[1]["chat"]
    node = tmp_path / schema["Query"] / "POST"
    node.mkdir(parents=True)
    (node / "exec").write_text("unchanged")
    os.mkfifo(node / "result.json")
    with pytest.raises(Unavailable):
        FifoClient(tmp_path).execute(schema, {})
    assert (node / "exec").read_text() == "unchanged"


def test_timeout_keeps_staging_file_and_does_not_retry(filesystem_api):
    class TimedOutClient:
        calls = 0
        def execute(self, schema, args):
            self.calls += 1
            self.uri = args["-URI"]
            raise QueryTimeout("Completion is unknown")
    backend = TimedOutClient()
    app = create_app(filesystem_api[2], backend)
    response = app.test_client().put(path(filesystem_api, "rag_add"), data=b"Retain me", content_type="application/octet-stream")
    assert response.status_code == 504
    assert response.json["completion_unknown"] is True
    assert backend.calls == 1
    assert os.path.exists(backend.uri)


@pytest.mark.parametrize("raw,status", [(b"not JSON", 502), (b"[]", 502), (b'{}', 502), (b'{"error_code":-1,"error_msg":"failed"}', 502)])
def test_backend_failure_is_not_reported_as_success(filesystem_api, raw, status):
    class BrokenClient:
        def execute(self, schema, args):
            return raw
    app = create_app(filesystem_api[2], BrokenClient())
    response = app.test_client().post(path(filesystem_api, "chat"), json={"user_prompt": "Hello"})
    assert response.status_code == status


def test_agent_mount_mapping(filesystem_api):
    config = json.loads(filesystem_api[2].read_text())
    config["agent_api_mount"] = "/agent-api"
    filesystem_api[2].write_text(json.dumps(config))
    class Backend:
        def execute(self, schema, args):
            assert args["-URI"].startswith("/agent-api/.http_ambassador/staging/")
            return b'{"error_code":0,"doc_id":"mapped","chunk_ids":[]}'
    app = create_app(filesystem_api[2], Backend())
    response = app.test_client().put(path(filesystem_api, "rag_add"), data=b"Mapped", content_type="application/octet-stream")
    assert response.status_code == 200


def test_completed_sessions_are_reused_without_removing_agent_fifos(app, filesystem_api):
    url = path(filesystem_api, "chat")
    client = app.test_client()
    assert client.post(url, json={"user_prompt": "First"}).json["response"] == "First"
    assert client.post(url, json={"user_prompt": "Second"}).json["response"] == "Second"
    schema = filesystem_api[1]["chat"]
    node = filesystem_api[0] / schema["Query"] / schema["Method"]
    assert len(list(node.glob("result.json_http_*"))) == 1


@pytest.mark.parametrize("create_result", [False, True], ids=["missing-result", "stalled-result-writer"])
def test_result_wait_and_read_have_bounded_deadlines(tmp_path, filesystem_api, create_result):
    schema = filesystem_api[1]["chat"]
    node = tmp_path / schema["Query"] / "POST"
    node.mkdir(parents=True)
    for name in ("exec", "result.json"):
        os.mkfifo(node / name)
    finish = threading.Event()
    def stalled_agent():
        with (node / "exec").open() as input_pipe:
            command = input_pipe.read()
        if create_result:
            session = re.search(r"SESSION_ID=(http_[a-f0-9]+)", command)[1]
            result = node / ("result.json_" + session)
            os.mkfifo(result)
            with result.open("w"):
                finish.wait(2)  # Writer is connected but never sends data.
    thread = threading.Thread(target=stalled_agent, daemon=True)
    thread.start()
    start = time.monotonic()
    try:
        with pytest.raises(QueryTimeout):
            FifoClient(tmp_path, timeout_seconds=0.1).execute(schema, {"-user_prompt": "Hello"})
        assert time.monotonic() - start < 1
    finally:
        finish.set()
        thread.join(timeout=1)
    assert not thread.is_alive()


def test_oversized_result_is_drained_and_next_request_succeeds(filesystem_api):
    api, schemas, _ = filesystem_api
    client = FifoClient(api, timeout_seconds=5, max_result_bytes=10)
    with pytest.raises(InvalidResult):
        client.execute(schemas["chat"], {"-user_prompt": "A large reply", "-system_prompt": "Rules"})
    client.max_result_bytes = 1024
    result = json.loads(client.execute(schemas["chat"], {"-user_prompt": "Next", "-system_prompt": "Rules"}))
    assert result["response"] == "Next"
