import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading


if Path("/package/streaming_directory_upload_processor.py").exists():
    PROCESSOR = Path("/package/streaming_directory_upload_processor.py")
    SCHEMA = Path("/package/API/streaming_directory_upload.json")
else:
    ROOT = Path(__file__).parents[4]
    PROCESSOR = ROOT / "utility/file-uploader/streaming_directory_upload_processor.py"
    SCHEMA = ROOT / "utility/file-uploader/API/streaming_directory_upload.json"


def arguments(destination, workers="2"):
    return [
        "metadata", "{}", "destination", str(destination),
        "preferred_directory", "tree", "workers", workers,
        "file_regex", ".*", "conflict_policy", "fail",
        "StatusHeartbeatIntervalSec", "1", "SESSION_ID", "directory-test",
    ]


def load_processor_module():
    spec = importlib.util.spec_from_file_location("directory_processor", PROCESSOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schema_declares_directory_transport_contract():
    schema = json.loads(SCHEMA.read_text())
    assert schema["Query"] == "+/streaming_directory_upload"
    assert schema["Params"]["workers"] == "4"
    assert schema["Params"]["conflict_policy"] == "fail"
    assert "StatusHeartbeatIntervalSec" in schema["Params"]


def test_preflight_and_channel_preparation():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        request = root / "request"
        destination = root / "uploads"
        staging = root / "staging"
        request.mkdir()
        destination.mkdir()
        environment = {**os.environ, "FILE_UPLOADER_STAGING_ROOT": str(staging)}
        checked = subprocess.run(
            [sys.executable, str(PROCESSOR), "--request-directory", str(request),
             "--check-arguments", "--", *arguments(destination)],
            text=True, capture_output=True, env=environment, timeout=3,
        )
        assert checked.returncode == 0, checked.stdout + checked.stderr
        prepared = subprocess.run(
            [sys.executable, str(PROCESSOR), "--request-directory", str(request),
             "--prepare-api-channel", "--", *arguments(destination)],
            text=True, capture_output=True, env=environment, timeout=3,
        )
        assert prepared.returncode == 0, prepared.stdout + prepared.stderr
        report = json.loads(prepared.stdout)
        assert report["input_type"] == "DIRECTORY"
        assert report["status_type"] == "FIFO[]"
        assert report["protocol"] == "cmvp.directory-upload.v1"
        assert Path(report["input"]).is_symlink()
        assert Path(report["input"]).resolve().parent == staging.resolve()
        assert len(report["status"]) == 2
        assert all(stat.S_ISFIFO(Path(path).stat().st_mode) for path in report["status"])


def test_preflight_rejects_invalid_worker_regex_and_session():
    with tempfile.TemporaryDirectory() as temporary:
        request = Path(temporary) / "request"
        destination = Path(temporary) / "uploads"
        request.mkdir()
        destination.mkdir()
        for changed in (
            arguments(destination, workers="0"),
            [*arguments(destination)[:-8], "file_regex", "[", *arguments(destination)[-6:]],
            [*arguments(destination)[:-2], "SESSION_ID", "x" * 119],
        ):
            result = subprocess.run(
                [sys.executable, str(PROCESSOR), "--request-directory", str(request),
                 "--check-arguments", "--", *changed],
                text=True, capture_output=True, timeout=3,
            )
            assert result.returncode != 0


def test_concurrent_nested_allocations_are_individually_framed():
    processor = load_processor_module()
    with tempfile.TemporaryDirectory() as temporary:
        api = Path(temporary)
        exec_fifo = api / "exec"
        os.mkfifo(exec_fifo)
        requests = []

        def server():
            for _ in range(2):
                request = exec_fifo.read_text()
                requests.append(request)
                session = request.removeprefix("SESSION_ID=")
                handshake = api / f"result.json_{session}"
                os.mkfifo(handshake)
                handshake.write_text(json.dumps({"session": session}))
                handshake.unlink()

        server_thread = threading.Thread(target=server)
        server_thread.start()
        reports = {}

        def allocate(session):
            reports[session] = processor.allocate_nested_upload(
                api, api / f"result.json_{session}", f"SESSION_ID={session}",
            )

        workers = [threading.Thread(target=allocate, args=(session,))
                   for session in ("one", "two")]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=3)
            assert not worker.is_alive()
        server_thread.join(timeout=3)
        assert not server_thread.is_alive()
        assert sorted(requests) == ["SESSION_ID=one", "SESSION_ID=two"]
        assert reports == {"one": {"session": "one"}, "two": {"session": "two"}}
