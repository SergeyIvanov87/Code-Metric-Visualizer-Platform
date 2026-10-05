import importlib.util
import json
from pathlib import Path
import sys


MODULE_PATH = Path(__file__).parents[1] / "sources/rag_bulk_add.py"
sys.path.insert(0, str(Path(__file__).parents[3] / "common/modules"))
spec = importlib.util.spec_from_file_location("rag_bulk_add", MODULE_PATH)
rag_bulk_add = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rag_bulk_add)


def test_document_type_groups_code_and_semantic_text_types():
    assert rag_bulk_add.document_type("src/example.py") == "txt,code"
    assert rag_bulk_add.document_type("README.md") == "txt,markdown"
    assert rag_bulk_add.document_type("records.json") == "txt,data"
    assert rag_bulk_add.document_type("index.html") == "txt,web"
    assert rag_bulk_add.document_type("NOTICE") == "txt,document"


def test_augmented_metadata_contains_every_path_component():
    assert rag_bulk_add.augmented_metadata(
        "project=demo", "source/tools/build.py"
    ) == "project=demo source tools build.py"


def test_values_accepts_only_bulk_query_parameters():
    parsed = rag_bulk_add.values(["-metadata", "team=docs", "SESSION_ID", "bulk-1"])
    assert parsed["metadata"] == "team=docs"
    assert parsed["SESSION_ID"] == "bulk-1"


def test_add_file_invokes_regular_rag_add_query(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(rag_bulk_add, "api_exec", lambda root, path: Path("/rag/exec"))

    def request(exec_fifo, arguments, session, timeout):
        calls.append((exec_fifo, arguments, session, timeout))
        return json.dumps({"error_code": 0, "doc_id": "doc-123"})

    monkeypatch.setattr(rag_bulk_add, "fifo_request", request)
    result = rag_bulk_add.add_file(
        {"metadata": "origin=test", "SESSION_ID": "bulk"},
        tmp_path, "src/main.rs", 7,
    )
    assert result["status"] == "added"
    assert result["doc_id"] == "doc-123"
    assert "-URI=" + str(tmp_path / "src/main.rs") in calls[0][1]
    assert "-doc_type=txt,code" in calls[0][1]
    assert "origin=test src main.rs" in calls[0][1]
