import json
from pathlib import Path
import sys

import pytest


SOURCES_DIR = Path(__file__).resolve().parents[1] / "sources"
sys.path.insert(0, str(SOURCES_DIR))
sys.path.insert(0, str(Path(__file__).parents[3] / "common/modules"))

from fs_api_wrappers import (
    execute_delete_doc_query,
    execute_put_doc_query,
    rag_add_file,
    start_uploader,
)


class FakeQuery:
    def __init__(self):
        self.exec_args = None

    def execute(self, timeout_elapsed, exec_args):
        self.exec_args = exec_args
        return True, timeout_elapsed

    def wait_result(self, timeout_elapsed, session_id, *args):
        return True, '{"error_code": 0, "unique_id": 123}', timeout_elapsed


class JsonQuery(FakeQuery):
    def __init__(self, result):
        super().__init__()
        self.result = result
        self.session_id = None

    def wait_result(self, timeout_elapsed, session_id, *args):
        self.session_id = session_id
        return True, self.result, timeout_elapsed


def test_execute_put_doc_query_omits_uri_when_doc_data_is_specified():
    query = FakeQuery()

    execute_put_doc_query(
        query,
        "session",
        10,
        None,
        "encoded-document",
        "base64,txt",
        "metadata",
    )

    assert query.exec_args == (
        "SESSION_ID=session -doc_type=base64,txt "
        '-metadata=metadata doc_data="encoded-document"'
    )
    assert "-URI" not in query.exec_args


def test_execute_put_doc_query_passes_uri_when_doc_data_is_not_specified():
    query = FakeQuery()

    execute_put_doc_query(
        query,
        "session",
        10,
        "/documents/example.txt",
        None,
        "txt",
        None,
    )

    assert query.exec_args == (
        "SESSION_ID=session -doc_type=txt -URI=/documents/example.txt"
    )
    assert "doc_data=" not in query.exec_args


def test_execute_put_doc_query_rejects_binary_doc_data():
    with pytest.raises(TypeError, match="doc_data must be textual data"):
        execute_put_doc_query(
            FakeQuery(),
            "session",
            10,
            None,
            b"encoded-document",
            "base64,txt",
            "metadata",
        )


def test_execute_put_doc_query_quotes_doc_data_for_dispatcher():
    query = FakeQuery()
    encoded_document = "prefix/with+shell-sensitive=base64"

    execute_put_doc_query(
        query,
        "session",
        10,
        None,
        encoded_document,
        "base64,txt",
        "metadata",
    )

    assert query.exec_args.endswith(f'doc_data="{encoded_document}"')


def test_execute_delete_doc_query_uses_dispatcher_ids_option():
    query = FakeQuery()

    execute_delete_doc_query(query, "session", 10, "12,13", "metadata")

    assert query.exec_args == "SESSION_ID=session -ids=12,13 -metadata=metadata"


def test_start_uploader_uses_precreated_query_handle(tmp_path):
    report = {"staging": "/stage", "events": "/events"}
    query = JsonQuery(json.dumps(report))
    config = {
        "WaitInitialQueryTimeoutSec": "60",
        "WaitQueryUpdateTimeoutSec": "10",
        "WaitResultConsumptionTimeoutSec": "60",
    }

    assert start_uploader(query, tmp_path, config, "uploader-session") == report
    assert query.session_id == "uploader-session"
    assert query.exec_args.startswith("SESSION_ID=uploader-session ")
    assert json.loads((tmp_path / "uploader.json").read_text()) == report


def test_rag_add_file_uses_precreated_query_and_preserves_unicode(tmp_path):
    query = JsonQuery('{"error_code": 0, "doc_id": "doc-123"}')
    relative = "données/résumé-数据.py"

    result = rag_add_file(
        query,
        "worker-session",
        {"metadata": "équipe=δοκιμή"},
        tmp_path,
        relative,
        7,
    )

    assert result["status"] == "added"
    assert result["doc_id"] == "doc-123"
    assert result["doc_type"] == "txt,code"
    assert query.session_id == "worker-session"
    assert f"SESSION_ID=worker-session" in query.exec_args
    assert json.dumps(
        str(tmp_path / relative), ensure_ascii=False
    ) in query.exec_args
    assert "équipe=δοκιμή,données,résumé-数据.py" in query.exec_args
    assert "\\u" not in query.exec_args
