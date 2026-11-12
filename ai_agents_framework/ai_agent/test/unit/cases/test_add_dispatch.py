"""Check routing without loading embedding models or contacting Chroma."""

import base64
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import rag_add
from fs_api_wrappers import rag_add_file


@pytest.mark.parametrize("uri", [None, "/stage/file with spaces.txt"])
@pytest.mark.parametrize("preserveOriginal", [0, 1])
def test_main_selects_uri_or_data_endpoint(monkeypatch, uri, preserveOriginal):
    schemas = {
        f"domain_ai_agent_rag_dispatcher_{name}_v1": name
        for name in ("put_doc", "put_doc_data", "attach_doc_chunk", "delete_doc")
    }
    monkeypatch.setattr("fs_api_wrappers.get_doc_dispatcher_queries", lambda *args: schemas)
    monkeypatch.setattr(rag_add, "create_api_query_interruptible", lambda root, schema, session: schema)
    collection = Mock()
    client = Mock()
    client.get_or_create_collection.return_value = collection
    monkeypatch.setitem(sys.modules, "chromadb", SimpleNamespace(HttpClient=lambda **kwargs: client))
    monkeypatch.setitem(sys.modules, "langchain_chroma", SimpleNamespace(Chroma=Mock()))
    model = SimpleNamespace(embed_documents=lambda texts: [[0.1]])
    monkeypatch.setitem(sys.modules, "embedding_model", SimpleNamespace(get_embedding_model=lambda: model))
    monkeypatch.setattr(rag_add, "split_document", lambda *args, **kwargs: [SimpleNamespace(page_content="text")])
    put = Mock(return_value={"unique_id": 123})
    monkeypatch.setattr(rag_add, "execute_put_doc_query", put)
    monkeypatch.setattr(rag_add, "execute_attach_doc_chunks_query", lambda *args: (["456"], [{"doc_id": 123}]))
    assert rag_add.main("/api", "domain", "outer", "db", 8000, uri, "metadata", "txt", "text", 20,
                        preserveOriginal=preserveOriginal) == (123, ["456"])
    assert put.call_args.args[0] == ("put_doc" if uri else "put_doc_data")
    assert put.call_args.kwargs["preserveOriginal"] == preserveOriginal
    assert put.call_args.args[4] == (None if uri else base64.b64encode(b"text").decode())
    assert collection.add.call_args.kwargs["embeddings"] == [[0.1]]


@pytest.mark.parametrize("preserveOriginal", ["0", "1"])
def test_bulk_worker_forwards_preservation_policy(monkeypatch, tmp_path, preserveOriginal):
    execute = Mock(return_value={"error_code": 0, "doc_id": 123})
    monkeypatch.setattr("fs_api_wrappers._execute_json_query", execute)
    rag_add_file(object(), "session", {"metadata": "", "preserveOriginal": preserveOriginal},
                 tmp_path, "file with spaces.txt", 1)
    assert f"preserveOriginal={preserveOriginal}" in execute.call_args.args[3]
