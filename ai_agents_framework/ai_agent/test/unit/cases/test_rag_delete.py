from pathlib import Path
import sys

import pytest


SOURCES_DIR = Path("/package")
if not SOURCES_DIR.is_dir():
    SOURCES_DIR = Path(__file__).resolve().parents[3] / "sources"
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


def test_parse_ids_keeps_selection_compact():
    assert parse_ids("3-1000000000, 4,3") == "3-1000000000, 4,3"


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


def test_range_deletion_passes_ranges_to_dispatcher_and_reports_missing(monkeypatch, tmp_path):
    collection = FakeCollection()
    monkeypatch.setattr(
        "rag_delete.get_normalized_api_queries",
        lambda *args: {"delete_doc": Path("delete")},
    )
    monkeypatch.setattr("rag_delete.generate_inner_session_id", lambda *args: "inner")
    monkeypatch.setattr("rag_delete.create_api_query_interruptible", lambda *args: object())
    def delete_query(*args, **kwargs):
        assert kwargs["doc_id"] == "7-10, 8,20-21"
        return {"error_code": 0, "not_found": [9, 10, 20, 21]}
    monkeypatch.setattr("rag_delete.execute_delete_doc_query", delete_query)
    monkeypatch.setattr("rag_delete.chromadb.HttpClient", lambda **kwargs: FakeClient(collection))

    result = main(tmp_path, "service", "outer", "db", 8000, "7-10, 8,20-21", None)

    assert collection.where == {"$or": [
        {"$and": [{"doc_id": {"$gte": 7}}, {"doc_id": {"$lte": 10}}]},
        {"doc_id": {"$eq": 8}},
        {"$and": [{"doc_id": {"$gte": 20}}, {"doc_id": {"$lte": 21}}]},
    ]}
    assert collection.deleted_ids == ["21", "22"]
    assert result["not_found"] == [9, 10, 20, 21]


def test_dispatcher_failure_prevents_vector_deletion(monkeypatch, tmp_path):
    collection = FakeCollection()
    monkeypatch.setattr("rag_delete.get_normalized_api_queries", lambda *args: {"delete_doc": Path("delete")})
    monkeypatch.setattr("rag_delete.generate_inner_session_id", lambda *args: "inner")
    class FailedDeleteQuery:
        def execute(self, timeout_elapsed, arguments):
            return True, timeout_elapsed

        def wait_result(self, timeout_elapsed, *args):
            return True, '{"error_code":1,"error_msg":"Could not delete file storage records: [7]","not_found":[]}', timeout_elapsed

    monkeypatch.setattr("rag_delete.create_api_query_interruptible", lambda *args: FailedDeleteQuery())
    monkeypatch.setattr("rag_delete.chromadb.HttpClient", lambda **kwargs: FakeClient(collection))

    with pytest.raises(RuntimeError, match="Could not delete file storage records"):
        main(tmp_path, "service", "outer", "db", 8000, "7-10", None)
    assert collection.deleted_ids is None


def test_range_predicate_selects_inclusive_bounds_in_chroma():
    import chromadb
    from rag_delete import _document_filter

    client = chromadb.EphemeralClient()
    collection = client.create_collection("range-predicate-test")
    try:
        collection.add(
            ids=["6", "7", "8", "9", "10", "20", "21"],
            embeddings=[[1.0, 0.0]] * 7,
            metadatas=[{"doc_id": n} for n in [6, 7, 8, 9, 10, 20, 21]],
        )
        selected = collection.get(where=_document_filter("7-9,20"))
        assert set(selected["ids"]) == {"7", "8", "9", "20"}
    finally:
        client.delete_collection("range-predicate-test")
