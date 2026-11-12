"""Check routing without loading embedding models or contacting Chroma."""

import base64
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import rag_add
import rag_add_data
import rag_add_utils
from fs_api_wrappers import rag_add_file


@pytest.mark.parametrize("failure_stage", [None, "chunks", "chroma"])
@pytest.mark.parametrize("uri", [None, "/stage/file with spaces.txt"])
@pytest.mark.parametrize("preserveOriginal", [0, 1])
def test_main_selects_uri_or_data_endpoint(monkeypatch, tmp_path, uri, preserveOriginal, failure_stage):
    schemas = {
        f"domain_ai_agent_rag_dispatcher_{name}_v1": name
        for name in ("put_doc", "put_doc_data", "attach_doc_chunk", "delete_doc")
    }
    monkeypatch.setattr("fs_api_wrappers.get_doc_dispatcher_queries", lambda *args: schemas)
    monkeypatch.setattr(rag_add_utils, "create_api_query_interruptible", lambda root, schema, session: schema)
    if uri:
        uri = str(tmp_path / "file with spaces.txt")
        __import__("pathlib").Path(uri).write_bytes(b"text\r\n")
    collection = Mock()
    client = Mock()
    client.get_or_create_collection.return_value = collection
    monkeypatch.setitem(sys.modules, "chromadb", SimpleNamespace(HttpClient=lambda **kwargs: client))
    monkeypatch.setitem(sys.modules, "langchain_chroma", SimpleNamespace(Chroma=Mock()))
    model = SimpleNamespace(embed_documents=lambda texts: [[0.1]])
    monkeypatch.setitem(sys.modules, "embedding_model", SimpleNamespace(get_embedding_model=lambda: model))
    split = Mock(return_value=[SimpleNamespace(page_content="text")])
    monkeypatch.setattr(rag_add_utils, "split_document", split)
    put = Mock(return_value={"unique_id": 123})
    monkeypatch.setattr(rag_add, "execute_put_doc_query", put)
    monkeypatch.setattr(rag_add_utils, "execute_attach_doc_chunks_query", lambda *args: (["456"], [{"doc_id": 123}]))
    monkeypatch.setattr(rag_add_data, "execute_put_doc_data_query", put)
    rollback = Mock()
    monkeypatch.setattr(rag_add_utils, "execute_delete_doc_query", rollback)
    if failure_stage == "chunks":
        monkeypatch.setattr(rag_add_utils, "execute_attach_doc_chunks_query", Mock(side_effect=RuntimeError("chunk failure")))
    if failure_stage == "chroma":
        collection.add.side_effect = RuntimeError("chroma failure")
    if failure_stage:
        with pytest.raises(RuntimeError, match="Rollback was finished"):
            if uri:
                rag_add.main("/api", "domain", "outer", "db", 8000, uri, "metadata", "txt", 20, preserveOriginal=preserveOriginal)
            else:
                rag_add_data.main("/api", "domain", "outer", "db", 8000, "text", "metadata", "txt", 20)
        assert rollback.call_args.args[3] == 123
        return
    if uri:
        result = rag_add.main("/api", "domain", "outer", "db", 8000, uri, "metadata", "txt", 20,
                              preserveOriginal=preserveOriginal)
    else:
        result = rag_add_data.main("/api", "domain", "outer", "db", 8000, "text", "metadata", "txt", 20)
    assert result == (123, ["456"])
    assert split.call_args.args[0] == ("text\r\n" if uri else "text")
    assert put.call_args.args[0] == ("put_doc" if uri else "put_doc_data")
    if uri:
        assert put.call_args.args[-1] == preserveOriginal
        assert put.call_args.args[3] == uri
    else:
        assert put.call_args.args[3] == base64.b64encode(b"text").decode()
    assert collection.add.call_args.kwargs["embeddings"] == [[0.1]]


@pytest.mark.parametrize("preserveOriginal", ["0", "1"])
def test_bulk_worker_forwards_preservation_policy(monkeypatch, tmp_path, preserveOriginal):
    execute = Mock(return_value={"error_code": 0, "doc_id": 123})
    monkeypatch.setattr("fs_api_wrappers._execute_json_query", execute)
    rag_add_file(object(), "session", {"metadata": "", "preserveOriginal": preserveOriginal},
                 tmp_path, "file with spaces.txt", 1)
    assert f"preserveOriginal={preserveOriginal}" in execute.call_args.args[3]
