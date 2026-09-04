from pathlib import Path
import sys

import pytest


SOURCES_DIR = Path(__file__).resolve().parents[1] / "sources"
sys.path.insert(0, str(SOURCES_DIR))

from rag_sync import (
    ChromaSyncState,
    RagSyncProgress,
    extract_chunk_records,
    finalize_chroma_reconciliation,
    reconcile_chroma,
    reconcile_chroma_pages,
)


class FakeCollection:
    def __init__(self, ids):
        self.ids = set(ids)
        self.upserts = []
        self.deletions = []

    def get(self, include):
        assert include == []
        return {"ids": sorted(self.ids)}

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)
        self.ids.update(kwargs["ids"])

    def delete(self, ids):
        self.deletions.extend(ids)
        self.ids.difference_update(ids)


class FakeEmbeddingModel:
    def __init__(self):
        self.texts = []

    def embed_documents(self, texts):
        self.texts.extend(texts)
        return [[float(len(text))] for text in texts]


def test_reconcile_chroma_accumulates_batches_before_removing_non_chunk_ids():
    collection = FakeCollection({"11", "21", "stale", "1"})
    embedding_model = FakeEmbeddingModel()
    first_page = {"docs": [{"id": 1, "chunks": [11, 12]}]}
    second_page = {"docs": [{"id": 2, "chunks": [21]}]}
    chunk_texts = {"11": "first", "12": "second", "21": "third"}
    state = ChromaSyncState(initial_chroma_ids=set(collection.ids))

    reconcile_chroma(
        collection,
        embedding_model,
        first_page,
        chunk_texts.__getitem__,
        state,
    )
    assert collection.ids == {"1", "11", "12", "21", "stale"}
    assert collection.deletions == []

    reconcile_chroma(
        collection,
        embedding_model,
        second_page,
        chunk_texts.__getitem__,
        state,
    )
    result = finalize_chroma_reconciliation(collection, state)

    assert result == {
        "created": ["12"],
        "updated": ["11", "21"],
        "deleted": ["1", "stale"],
        "not_changed": [],
        "synchronized_count": 3,
        "initial_chroma_records": 4,
        "chroma_size": 3,
    }
    assert collection.ids == {"11", "12", "21"}
    assert embedding_model.texts == ["first", "second", "third"]
    assert [call["ids"] for call in collection.upserts] == [["11"], ["12"], ["21"]]
    assert collection.upserts[0]["metadatas"] == [
        {"doc_id": 1, "chunk_num": 0, "chunk_id": 11}
    ]


def test_reconcile_chroma_pages_advances_offset_by_returned_document_count():
    collection = FakeCollection({"stale"})
    embedding_model = FakeEmbeddingModel()
    calls = []
    pages = {
        0: {
            "offset": 0,
            "limit": 2,
            "remaining": 1,
            "docs": [
                {"id": 1, "chunks": [11]},
                {"id": 2, "chunks": [21]},
            ],
        },
        2: {
            "offset": 2,
            "limit": 1,
            "remaining": 0,
            "docs": [{"id": 3, "chunks": [31]}],
        },
    }

    def get_docs_page(offset, limit):
        calls.append((offset, limit))
        if offset == 2:
            assert collection.deletions == []
        return pages[offset]

    result = reconcile_chroma_pages(
        collection,
        embedding_model,
        batch_size=2,
        get_docs_page=get_docs_page,
        read_chunk=lambda chunk_id: f"text-{chunk_id}",
    )

    assert calls == [(0, 2), (2, 2)]
    assert result["created"] == ["11", "21", "31"]
    assert result["deleted"] == ["stale"]
    assert collection.ids == {"11", "21", "31"}


def test_progress_preserves_confirmed_upserts_before_failure():
    collection = FakeCollection({"stale"})
    progress = RagSyncProgress(
        chroma=ChromaSyncState(initial_chroma_ids=set(collection.ids)),
        filesystem_db_sync={"created": 2},
    )
    docs = {"docs": [{"id": 1, "chunks": [11, 12]}]}

    with pytest.raises(RuntimeError, match="could not find chunk id 12"):
        reconcile_chroma(
            collection,
            FakeEmbeddingModel(),
            docs,
            lambda chunk_id: "first" if chunk_id == "11" else "<Not found ID>",
            progress.chroma,
        )

    assert progress.to_result() == {
        "created": ["11"],
        "updated": [],
        "deleted": [],
        "not_changed": [],
        "synchronized_count": 1,
        "initial_chroma_records": 1,
        "chroma_size": 2,
        "filesystem_db_sync": {"created": 2},
    }
    assert collection.ids == {"11", "stale"}


def test_progress_preserves_confirmed_deletion_batches_before_failure():
    class FailingSecondDeleteCollection(FakeCollection):
        def __init__(self, ids):
            super().__init__(ids)
            self.delete_calls = 0

        def delete(self, ids):
            self.delete_calls += 1
            if self.delete_calls == 2:
                raise RuntimeError("delete failed")
            super().delete(ids)

    initial_ids = {f"stale-{index}" for index in range(1001)}
    collection = FailingSecondDeleteCollection(initial_ids)
    progress = RagSyncProgress(
        chroma=ChromaSyncState(initial_chroma_ids=set(initial_ids))
    )

    with pytest.raises(RuntimeError, match="delete failed"):
        finalize_chroma_reconciliation(collection, progress.chroma)

    result = progress.to_result()
    assert len(result["deleted"]) == 1000
    assert result["synchronized_count"] == 0
    assert result["chroma_size"] == 1
    assert len(collection.ids) == 1


def test_reconcile_chroma_does_not_delete_stale_ids_when_a_chunk_read_fails():
    collection = FakeCollection({"stale"})
    docs = {"docs": [{"id": 1, "chunks": [11]}]}
    state = ChromaSyncState(initial_chroma_ids=set(collection.ids))

    with pytest.raises(RuntimeError, match="could not find chunk id 11"):
        reconcile_chroma(
            collection,
            FakeEmbeddingModel(),
            docs,
            lambda _chunk_id: "<Not found ID>",
            state,
        )

    assert collection.ids == {"stale"}
    assert collection.deletions == []


def test_extract_chunk_records_rejects_duplicate_chunk_ids():
    with pytest.raises(RuntimeError, match="duplicate chunk id: 11"):
        extract_chunk_records(
            {
                "docs": [
                    {"id": 1, "chunks": [11]},
                    {"id": 2, "chunks": [11]},
                ]
            }
        )
