"""Query discovery accepts actual API paths as well as discovery keys."""
import pytest
from fs_api_wrappers import get_normalized_api_queries
from rag_bulk_add import API_QUERY_PATTERNS


@pytest.mark.parametrize("query", [
    "domain/ai_agent/rag/add_doc/v1/",
    "domain/ai_agent/rag/add_doc/v1/PUT",
    "domain/ai_agent/rag_add_doc/v1/PUT",
    "domain_ai_agent_rag_add_doc_v1",
])
def test_uri_query_matches_without_matching_data_query(monkeypatch, query):
    schema = {"Query": query}
    monkeypatch.setattr("fs_api_wrappers.get_doc_dispatcher_queries", lambda *args: {"unrelated-key": schema})
    assert get_normalized_api_queries("/api", "domain", {"rag_add": API_QUERY_PATTERNS["rag_add"]})["rag_add"] is schema
    assert not API_QUERY_PATTERNS["rag_add"].match("domain/ai_agent/rag/add_doc_data/v1/")
