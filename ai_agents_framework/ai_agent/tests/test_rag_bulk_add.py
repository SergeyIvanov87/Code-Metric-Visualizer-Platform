import importlib.util
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import threading


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
    previous = os.umask(0o077)
    try:
        prepared = rag_bulk_add.prepare(request, [])
    finally:
        os.umask(previous)
    assert Path(prepared["events"]).stat().st_mode & 0o777 == 0o644
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
    ) == "project=demo,source,tools,build.py"
    assert rag_bulk_add.augmented_metadata("", "test/file.txt") == "test,file.txt"
    assert rag_bulk_add.augmented_metadata("1", "test/compose-functional.dev.yaml") == "1,test,compose-functional.dev.yaml"


def test_values_accepts_only_bulk_query_parameters():
    parsed = rag_bulk_add.values([
        "-metadata", "team=docs", "SESSION_ID", "bulk-1", "workers", "8",
    ])
    assert parsed["metadata"] == "team=docs"
    assert parsed["SESSION_ID"] == "bulk-1"
    assert parsed["workers"] == "8"
    assert rag_bulk_add.values([])["workers"] == "4"


def test_values_rejects_invalid_worker_count():
    for workers in ("0", "-1", "many"):
        try:
            rag_bulk_add.values(["workers", workers])
        except ValueError as error:
            assert str(error) == "workers must be a positive integer"
        else:
            raise AssertionError(f"accepted invalid worker count: {workers}")


def test_add_file_invokes_regular_rag_add_query(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(rag_bulk_add, "api_exec", lambda root, path: Path("/rag/exec"))

    def request(exec_fifo, arguments, session, timeout):
        calls.append((exec_fifo, arguments, session, timeout))
        return json.dumps({"error_code": 0, "doc_id": "doc-123"})

    monkeypatch.setattr(rag_bulk_add, "fifo_request", request)
    result = rag_bulk_add.add_file(
        {"metadata": "origin=test", "SESSION_ID": "bulk", "RUN_ID": "run-456"},
        tmp_path, "src/main.rs", 7,
    )
    assert result["status"] == "added"
    assert result["doc_id"] == "doc-123"
    assert "-URI=" + json.dumps(str(tmp_path / "src/main.rs")) in calls[0][1]
    assert "-doc_type=txt,code" in calls[0][1]
    assert "origin=test,src,main.rs" in calls[0][1]
    assert calls[0][2] == "rag-bulk-add-bulk-run-456-task-7"
    assert_utc_timestamp(result["timestamp"])


def assert_utc_timestamp(value):
    assert value.endswith("Z")
    datetime.fromisoformat(value.removesuffix("Z") + "+00:00")


def test_run_processes_files_in_parallel_and_publishes_in_sequence(
    monkeypatch, tmp_path, capsys,
):
    request = tmp_path / "request"
    request.mkdir()
    source_events = tmp_path / "source-events"
    source_events.write_text("")
    (request / "stage.json").write_text(json.dumps({
        "staging": str(tmp_path / "stage"),
        "events": str(tmp_path / "result-events"),
    }))
    (request / "uploader.json").write_text(json.dumps({
        "events": str(source_events),
    }))
    events = [
        {"status": "ready", "path": f"document-{index}.txt"}
        for index in range(4)
    ]
    monkeypatch.setattr(
        rag_bulk_add, "parse_directory_event_stream", lambda _stream: iter(events)
    )
    barrier = threading.Barrier(4)
    thread_names = set()
    run_ids = set()

    def add_file(_config, _stage, path, sequence):
        thread_names.add(threading.current_thread().name)
        run_ids.add(_config["RUN_ID"])
        barrier.wait(timeout=5)
        return {
            "sequence": sequence, "status": "added", "path": path,
            "doc_id": f"doc-{sequence}",
        }

    monkeypatch.setattr(rag_bulk_add, "add_file", add_file)
    published = []
    monkeypatch.setattr(
        rag_bulk_add, "publish_event", lambda _writer, event: published.append(event)
    )
    options = type("Options", (), {"request_directory": request})()

    assert rag_bulk_add.run(options, ["workers", "4"]) == 0

    result = json.loads(capsys.readouterr().out)
    assert len(thread_names) == 4
    assert len(run_ids) == 1
    assert [event["sequence"] for event in published] == [1, 2, 3, 4, 5]
    assert published[-1]["sequence"] == 5
    assert published[-1]["status"] == "terminated"
    assert published[-1]["added_count"] == 4
    assert published[-1]["failed_count"] == 0
    assert_utc_timestamp(published[-1]["timestamp"])
    assert result["timestamp"] == published[-1]["timestamp"]
    for outcome in result["added"]:
        assert_utc_timestamp(outcome["timestamp"])
    assert [outcome["sequence"] for outcome in result["added"]] == [1, 2, 3, 4]
    assert result["failed"] == []


def test_worker_failure_outcome_has_completion_timestamp(monkeypatch):
    input_queue = rag_bulk_add.Queue()
    outcome_queue = rag_bulk_add.Queue()
    input_queue.put(({"path": "broken.txt"}, 3))
    input_queue.put(rag_bulk_add.TERMINATE_WORKER)

    def fail(*_args):
        raise RuntimeError("add failed")

    monkeypatch.setattr(rag_bulk_add, "add_file", fail)
    rag_bulk_add.add_file_worker({}, Path("/stage"), input_queue, outcome_queue)

    outcome = outcome_queue.get_nowait()
    assert outcome["sequence"] == 3
    assert outcome["status"] == "failed"
    assert outcome["error"] == "add failed"
    assert_utc_timestamp(outcome["timestamp"])
