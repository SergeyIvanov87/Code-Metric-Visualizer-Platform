from pathlib import Path
import sys

import pytest


SOURCES_DIR = Path(__file__).resolve().parents[1] / "sources"
sys.path.insert(0, str(SOURCES_DIR))

from rag_delete import main, parse_ids


class FakeCollection:
    def __init__(self):
        self.where = None
        self.deleted_ids = None

    def get(self, where):
        self.where = where
        return {"ids": ["21", "22"]}

    def delete(self, ids):
        self.deleted_ids = ids


class FakeClient:
    def __init__(self, collection):
        self.collection = collection

    def get_collection(self, name):
        assert name == "service"
        return self.collection


def test_parse_ids_deduplicates_ids():
    assert parse_ids("3, 4,3") == [3, 4]


def test_parse_ids_rejects_invalid_ids():
    with pytest.raises(Exception, match="comma-separated integers"):
        parse_ids("3,nope")


def test_main_deletes_dispatcher_records_before_chroma(monkeypatch, tmp_path):
    collection = FakeCollection()
    events = []
    monkeypatch.setattr(
        "rag_delete.get_normalized_api_queries",
        lambda *args: {"delete_doc": Path("delete")},
    )
    monkeypatch.setattr("rag_delete.generate_inner_session_id", lambda *args: "inner")
    monkeypatch.setattr("rag_delete.create_api_query_interruptible", lambda *args: object())
    monkeypatch.setattr(
        "rag_delete.execute_delete_doc_query",
        lambda *args, **kwargs: events.append("dispatcher") or {"error_code": 0},
    )
    monkeypatch.setattr(
        "rag_delete.chromadb.HttpClient",
        lambda **kwargs: FakeClient(collection),
    )
    original_delete = collection.delete
    collection.delete = lambda ids: events.append("chroma") or original_delete(ids)

    result = main(tmp_path, "service", "outer", "db", 8000, [7, 8], None)

    assert collection.where == {"doc_id": {"$in": [7, 8]}}
    assert collection.deleted_ids == ["21", "22"]
    assert events == ["dispatcher", "chroma"]
    assert result["deleted_chunk_ids"] == ["21", "22"]
