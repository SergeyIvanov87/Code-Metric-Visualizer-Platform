"""Filename defaults and propagation for document-data ingestion."""
from datetime import datetime, timezone
from types import SimpleNamespace
import sys
from unittest.mock import Mock

import pytest
import rag_add_data


@pytest.mark.parametrize("filename", ["provided document.txt", None])
def test_filename_reaches_dispatcher(monkeypatch, filename):
    monkeypatch.setitem(sys.modules, "embedding_model", SimpleNamespace(
        get_embedding_model=lambda: SimpleNamespace(embed_documents=lambda texts: [[0.1]])))
    monkeypatch.setattr(rag_add_data, "split_document", lambda *args, **kwargs: [SimpleNamespace(page_content="text")])
    monkeypatch.setattr(rag_add_data, "get_normalized_api_queries", lambda *args: {
        "put_doc_data": {}, "attach_doc_chunk": {}, "delete_doc": {}})
    monkeypatch.setattr(rag_add_data, "create_api_query_interruptible", lambda *args: object())
    put = Mock(return_value={"unique_id": 1})
    monkeypatch.setattr(rag_add_data, "execute_put_doc_data_query", put)
    monkeypatch.setattr(rag_add_data, "attach_chunks", lambda *args: (["2"], [{}]))
    monkeypatch.setattr(rag_add_data, "insert_embeddings", lambda *args: None)
    before = datetime.now(timezone.utc).strftime("%Y-%m-%d:%H:%M:%S_txt")
    rag_add_data.main("/api", "domain", "session", "db", 8000, "text", "metadata", "txt", 20, filename=filename)
    actual = put.call_args.kwargs["filename"]
    if filename:
        assert actual == filename
    else:
        after = datetime.now(timezone.utc).strftime("%Y-%m-%d:%H:%M:%S_txt")
        assert actual in (before, after)
