from pathlib import Path
import sys

import pytest


SOURCES_DIR = Path(__file__).resolve().parents[1] / "sources"
sys.path.insert(0, str(SOURCES_DIR))

from rag_search import parse_parameters, search_chroma


class NamedCollection:
    def __init__(self, name):
        self.name = name


class FakeCollection:
    def __init__(self, records):
        self.records = sorted(records, key=lambda item: item[1])
        self.request_counts = []

    def count(self):
        return len(self.records)

    def query(self, query_embeddings, n_results, include):
        assert query_embeddings == [[0.25, 0.75]]
        assert include == ["distances"]
        self.request_counts.append(n_results)
        records = self.records[:n_results]
        return {
            "ids": [[record_id for record_id, _ in records]],
            "distances": [[distance for _, distance in records]],
        }


class FakeClient:
    def __init__(self, collections):
        self.collections = collections

    def list_collections(self):
        return [NamedCollection(name) for name in reversed(self.collections)]

    def get_collection(self, name):
        return self.collections[name]


class FakeEmbedder:
    def __init__(self):
        self.queries = []

    def embed_query(self, query):
        self.queries.append(query)
        return [0.25, 0.75]


class FakeDocumentStore:
    def __init__(self):
        self.ids = []

    def get_many(self, ids):
        self.ids = ids
        return {record_id: f"content-{record_id}" for record_id in ids}


def test_parse_parameters_validates_search_score_range_and_count():
    with pytest.raises(ValueError, match="search must not be empty"):
        parse_parameters([])
    with pytest.raises(ValueError, match="score_min must not be greater"):
        parse_parameters(
            ["search", "query", "score_min", "0.8", "score_max", "0.2"]
        )
    with pytest.raises(ValueError, match="count must be greater"):
        parse_parameters(["search", "query", "count", "0"])
    with pytest.raises(ValueError, match="invalid collection regex"):
        parse_parameters(["search", "query", "collection_use_regex", "["])


def test_search_filters_collections_range_and_global_count():
    alpha = FakeCollection(
        [("a-close", 0.1), ("a-good", 0.4), ("a-far", 0.8)]
    )
    beta = FakeCollection([("b-good", 0.3), ("b-far", 0.7)])
    archive = FakeCollection([("old", 0.25)])
    client = FakeClient({"alpha": alpha, "beta": beta, "archive": archive})
    embedder = FakeEmbedder()
    store = FakeDocumentStore()
    parameters = parse_parameters(
        [
            "search", "semantic query",
            "score_min", "0.2",
            "score_max", "0.6",
            "count", "2",
            "collection_use_regex", "^(alpha|beta|archive)$",
            "collection_avoid_regex", "archive",
        ]
    )

    result = search_chroma(client, embedder, store, parameters)

    assert result["collections"] == ["alpha", "beta"]
    assert result["count"] == 2
    assert result["documents"] == [
        {
            "collection": "beta",
            "id": "b-good",
            "score": 0.3,
            "content": "content-b-good",
        },
        {
            "collection": "alpha",
            "id": "a-good",
            "score": 0.4,
            "content": "content-a-good",
        },
    ]
    assert store.ids == ["b-good", "a-good"]
    assert embedder.queries == ["semantic query"]
    assert archive.request_counts == []


def test_search_expands_when_score_min_excludes_nearest_results():
    collection = FakeCollection(
        [("too-close-1", 0.1), ("too-close-2", 0.2), ("match", 0.4)]
    )
    parameters = parse_parameters(
        [
            "search", "query",
            "score_min", "0.3",
            "score_max", "0.5",
            "count", "1",
        ]
    )

    result = search_chroma(
        FakeClient({"all": collection}),
        FakeEmbedder(),
        FakeDocumentStore(),
        parameters,
    )

    assert [document["id"] for document in result["documents"]] == ["match"]
    assert collection.request_counts == [1, 2, 3]
