from pathlib import Path
import sys

import pytest


SOURCES_DIR = Path(__file__).resolve().parents[1] / "sources"
sys.path.insert(0, str(SOURCES_DIR))

from fs_api_wrappers import execute_put_doc_query


class FakeQuery:
    def __init__(self):
        self.exec_args = None

    def execute(self, timeout_elapsed, exec_args):
        self.exec_args = exec_args
        return True, timeout_elapsed

    def wait_result(self, timeout_elapsed, session_id, *args):
        return True, '{"error_code": 0, "unique_id": 123}', timeout_elapsed


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
