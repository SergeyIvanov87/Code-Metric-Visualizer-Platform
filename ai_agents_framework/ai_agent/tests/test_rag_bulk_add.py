import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys


MODULE_PATH = Path(__file__).parents[1] / "sources/rag_bulk_add.py"
sys.path.insert(0, str(Path(__file__).parents[3] / "common/modules"))
spec = importlib.util.spec_from_file_location("rag_bulk_add", MODULE_PATH)
rag_bulk_add = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rag_bulk_add)


def test_bulk_input_survives_api_volume_mount_relocation(monkeypatch, tmp_path):
    api = tmp_path / "container" / "api"
    request = api / "api.pmccabe_collector.restapi.org/ai_agent/rag/bulk_add/v1/POST/deferred-bulk"
    request.mkdir(parents=True)
    uploader_request = api / "api.pmccabe_collector.restapi.org/file-uploader/streaming_directory_events/POST/deferred-upload"
    uploader_request.mkdir(parents=True)
    uploader_path = Path(__file__).parents[3] / "utility/file-uploader/streaming_directory_events_processor.py"
    uploader_spec = importlib.util.spec_from_file_location("uploader", uploader_path)
    uploader = importlib.util.module_from_spec(uploader_spec)
    uploader_spec.loader.exec_module(uploader)
    monkeypatch.setenv("STAGING_ROOT", str(api / ".staging"))
    report = uploader.prepare(uploader_request, ["SESSION_ID", "bulk"])
    monkeypatch.setattr(rag_bulk_add, "start_uploader", lambda *_: report)
    monkeypatch.setenv("FS_API_CLIENT_GID", "0")
    ownership = []
    monkeypatch.setattr(rag_bulk_add.os, "chown", lambda *args: ownership.append(args))
    previous = os.umask(0o077)
    try:
        prepared = rag_bulk_add.prepare(request, [])
    finally:
        os.umask(previous)
    assert Path(prepared["events"]).stat().st_mode & 0o777 == 0o640
    assert ownership == [(Path(prepared["events"]), -1, 0)]
    assert not Path(os.readlink(prepared["input"])).is_absolute()
    assert Path(prepared["staging"]).is_relative_to(api)
    assert Path(prepared["staging"]).stat().st_mode & 0o777 == 0o777

    # A separate filesystem view catches links escaping the API mount boundary.
    host_api = tmp_path / "docker/volumes/api/_data"
    shutil.copytree(api, host_api, symlinks=True,
                    ignore=lambda _, names: [n for n in names if n in {"events", "seal"}])
    host_input = host_api / request.relative_to(api) / "input"
    assert host_input.resolve().is_relative_to(host_api)
    (host_input / "example.py").write_text("print('host upload')")
    assert (host_api / Path(prepared["staging"]).relative_to(api) / "example.py").read_text() == "print('host upload')"


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
    assert "-URI=" + json.dumps(str(tmp_path / "src/main.rs")) in calls[0][1]
    assert "-doc_type=txt,code" in calls[0][1]
    assert "origin=test src main.rs" in calls[0][1]
