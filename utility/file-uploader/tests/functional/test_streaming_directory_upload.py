import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading
import time


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


def wait_for_fifo(path, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if stat.S_ISFIFO(path.stat().st_mode):
                return path
        except FileNotFoundError:
            pass
        time.sleep(0.01)
    raise AssertionError(f"FIFO did not appear within {timeout} seconds: {path}")


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


def test_nested_worker_session_reuses_persistent_result_fifo():
    processor = load_processor_module()
    with tempfile.TemporaryDirectory() as temporary:
        api = Path(temporary)
        exec_fifo = api / "exec"
        result_fifo = api / "result.json_parent.worker-1"
        os.mkfifo(exec_fifo)
        os.mkfifo(result_fifo)
        requests = []

        def server():
            for sequence in (1, 2):
                requests.append(exec_fifo.read_text())
                result_fifo.write_text(json.dumps({"sequence": sequence}))

        server_thread = threading.Thread(target=server)
        server_thread.start()
        reports = [processor.allocate_nested_upload(
            api, result_fifo, "SESSION_ID=parent.worker-1",
        ) for _ in range(2)]
        server_thread.join(timeout=3)
        assert not server_thread.is_alive()
        assert requests == ["SESSION_ID=parent.worker-1"] * 2
        assert reports == [{"sequence": 1}, {"sequence": 2}]


def test_terminal_status_waits_briefly_for_a_late_reader():
    processor = load_processor_module()
    with tempfile.TemporaryDirectory() as temporary:
        status_fifo = Path(temporary) / "status-1"
        os.mkfifo(status_fifo)
        writer = processor.StatusWriter(status_fifo, 1)
        writer_thread = threading.Thread(
            target=writer.emit, args=("file.txt", 4, 4, "done"),
            kwargs={"terminal": True},
        )
        writer_thread.start()
        # Attach after the first nonblocking open has observed no reader.
        time.sleep(0.05)
        record = json.loads(status_fifo.open().readline())
        writer_thread.join(timeout=3)
        writer.close()
        assert not writer_thread.is_alive()
        assert record == {
            "worker_id": 1, "path": "file.txt", "bytes": 4,
            "total_bytes": 4, "status": "done",
        }


def test_running_container_uploads_more_files_than_workers_and_reports_status():
    api = Path(
        "/api/api.pmccabe_collector.restapi.org/file-uploader/"
        "streaming_directory_upload/POST"
    )
    if not Path("/api").is_dir():
        return
    wait_for_fifo(api / "exec", timeout=30)
    session = f"directory-functional-{os.getpid()}"
    (api / "exec").write_text(
        f"SESSION_ID={session} workers=4 preferred_directory={session} "
        "WaitInitialQueryTimeoutSec=5 WaitQueryUpdateTimeoutSec=0.2 "
        "WaitResultConsumptionTimeoutSec=5 StatusHeartbeatIntervalSec=0.05"
    )
    report = json.loads(wait_for_fifo(api / f"result.json_{session}").read_text())
    statuses = {path: [] for path in report["status"]}

    def consume_status(path):
        with Path(path).open() as stream:
            statuses[path].extend(json.loads(line) for line in stream)

    readers = [threading.Thread(target=consume_status, args=(path,))
               for path in report["status"]]
    for reader in readers:
        reader.start()
    staging = Path(report["input"])
    for number in range(8):
        (staging / f"file-{number}.txt").write_text(f"payload-{number}")
    result = json.loads(wait_for_fifo(Path(report["result"]), timeout=15).read_text())
    for reader in readers:
        reader.join(timeout=3)
        assert not reader.is_alive()
    assert result["error_code"] == "0"
    assert result["files_completed"] == "8/8"
    destination = Path(result["path"])
    assert len(list(destination.iterdir())) == 8
    done_paths = {
        record["path"] for records in statuses.values() for record in records
        if record["status"] == "done"
    }
    assert done_paths == {f"file-{number}.txt" for number in range(8)}
