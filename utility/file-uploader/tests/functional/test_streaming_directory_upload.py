import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace


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
        "file_allow_regex", ".*", "conflict_policy", "fail",
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
    assert schema["Params"]["file_allow_regex"] == ".*"
    assert schema["Params"]["file_skip_regex"] == "(?!)"
    assert schema["Params"]["dir_allow_regex"] == ".*"
    assert schema["Params"]["dir_skip_regex"] == (
        r"(?:^|.*/)(?:[.][^/]+|__pycache__|__pypackages__|node_modules)"
    )
    assert "file_regex" not in schema["Params"]
    assert schema["Params"]["conflict_policy"] == "fail"
    assert schema["Params"]["tolerate_errors"] == "false"
    assert "StatusHeartbeatIntervalSec" in schema["Params"]


def test_preflight_and_channel_preparation():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        request = root / "request"
        destination = root / "uploads"
        request.mkdir()
        destination.mkdir()
        checked = subprocess.run(
            [sys.executable, str(PROCESSOR), "--request-directory", str(request),
             "--check-arguments", "--", *arguments(destination)],
            text=True, capture_output=True, timeout=3,
        )
        assert checked.returncode == 0, checked.stdout + checked.stderr
        prepared = subprocess.run(
            [sys.executable, str(PROCESSOR), "--request-directory", str(request),
             "--prepare-api-channel", "--", *arguments(destination)],
            text=True, capture_output=True, timeout=3,
        )
        assert prepared.returncode == 0, prepared.stdout + prepared.stderr
        report = json.loads(prepared.stdout)
        assert report["input_type"] == "DIRECTORY"
        assert report["status_type"] == "FIFO[]"
        assert report["protocol"] == "cmvp.directory-upload.v1"
        input_path = Path(report["input"])
        assert input_path.is_dir()
        assert not input_path.is_symlink()
        assert input_path.parent == request
        source = root / "source-tree"
        source.mkdir()
        (source / "host-visible.txt").write_text("host copy")
        shutil.copytree(source, input_path / source.name)
        assert (input_path / source.name / "host-visible.txt").read_text() == "host copy"
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
            [*arguments(destination)[:-8], "file_allow_regex", "[",
             *arguments(destination)[-6:]],
            [*arguments(destination), "file_skip_regex", "["],
            [*arguments(destination), "dir_allow_regex", "["],
            [*arguments(destination), "dir_skip_regex", "["],
            [*arguments(destination), "file_regex", ".*"],
            [*arguments(destination)[:-2], "SESSION_ID", "x" * 119],
            [*arguments(destination), "tolerate_errors", "sometimes"],
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


def test_nested_upload_deletes_staging_source_after_confirmed_copy(monkeypatch):
    processor = load_processor_module()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        api = root / "api"
        destination = root / "destination"
        stage = root / "input"
        api.mkdir()
        destination.mkdir()
        stage.mkdir()
        input_fifo = api / "input"
        result_fifo = api / "result"
        os.mkfifo(input_fifo)
        os.mkfifo(result_fifo)
        source = stage / "source.txt"
        payload = b"confirmed payload"
        source.write_bytes(payload)
        received = []
        statuses = []

        monkeypatch.setattr(
            processor,
            "allocate_nested_upload",
            lambda *args: {
                "input": str(input_fifo),
                "result": str(result_fifo),
            },
        )

        def nested_server():
            received.append(input_fifo.read_bytes())
            result_fifo.write_text(json.dumps({
                "error_code": "0",
                "received_bytes": len(payload),
            }))

        server = threading.Thread(target=nested_server)
        server.start()
        writer = SimpleNamespace(
            emit=lambda *args, **kwargs: statuses.append((args, kwargs))
        )

        copied = processor.nested_upload(
            api, "parent", 1, source, "source.txt", destination, {}, writer,
            heartbeat=1, initial_timeout=1, update_timeout=1,
        )
        server.join(timeout=2)

        assert not server.is_alive()
        assert copied == len(payload)
        assert received == [payload]
        assert not source.exists()
        assert [entry[0][3] for entry in statuses] == ["done"]
        assert statuses[0][0][1:3] == (len(payload), len(payload))


def test_nested_upload_reports_in_progress_only_before_completion(monkeypatch):
    processor = load_processor_module()
    monkeypatch.setattr(processor, "CHUNK_SIZE", 4)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        api = root / "api"
        destination = root / "destination"
        stage = root / "input"
        api.mkdir()
        destination.mkdir()
        stage.mkdir()
        input_fifo = api / "input"
        result_fifo = api / "result"
        os.mkfifo(input_fifo)
        os.mkfifo(result_fifo)
        source = stage / "source.txt"
        payload = b"partial then complete"
        source.write_bytes(payload)
        statuses = []

        monkeypatch.setattr(
            processor,
            "allocate_nested_upload",
            lambda *args: {
                "input": str(input_fifo),
                "result": str(result_fifo),
            },
        )

        def nested_server():
            received = input_fifo.read_bytes()
            result_fifo.write_text(json.dumps({
                "error_code": "0",
                "received_bytes": len(received),
            }))

        server = threading.Thread(target=nested_server)
        server.start()
        writer = SimpleNamespace(
            emit=lambda *args, **kwargs: statuses.append((args, kwargs))
        )

        copied = processor.nested_upload(
            api, "parent", 1, source, "source.txt", destination, {}, writer,
            heartbeat=0.05, initial_timeout=1, update_timeout=1,
        )
        server.join(timeout=2)

        assert not server.is_alive()
        assert copied == len(payload)
        progress = [entry[0] for entry in statuses if entry[0][3] == "in progress"]
        completed = [entry[0] for entry in statuses if entry[0][3] == "done"]
        assert progress
        assert all(entry[1] < entry[2] for entry in progress)
        assert [(entry[1], entry[2]) for entry in completed] == [
            (len(payload), len(payload)),
        ]


def test_terminal_status_remains_queued_for_a_late_reader():
    processor = load_processor_module()
    with tempfile.TemporaryDirectory() as temporary:
        status_fifo = Path(temporary) / "status-1"
        os.mkfifo(status_fifo)
        writer = processor.StatusWriter(status_fifo, 1)
        # The immediate non-blocking attempt finds no reader, but the terminal
        # record remains available during the quiet period.
        writer.emit("file.txt", 4, 4, "done", terminal=True)
        received = []
        reader_thread = threading.Thread(
            target=lambda: received.append(json.loads(status_fifo.open().readline()))
        )
        reader_thread.start()
        time.sleep(0.05)
        assert writer.flush_pending()
        writer.close()
        reader_thread.join(timeout=3)
        assert not reader_thread.is_alive()
        assert received == [{
            "worker_id": 1, "path": "file.txt", "bytes": 4,
            "total_bytes": 4, "status": "done",
        }]


def test_status_writer_retains_all_events_between_reader_connections():
    processor = load_processor_module()
    with tempfile.TemporaryDirectory() as temporary:
        status_fifo = Path(temporary) / "status-1"
        os.mkfifo(status_fifo)
        writer = processor.StatusWriter(status_fifo, 1)

        first = []
        first_reader = threading.Thread(
            target=lambda: first.append(
                json.loads(status_fifo.open().readline())
            )
        )
        first_reader.start()
        time.sleep(0.05)
        writer.emit("initial.txt", 1, 1, "done")
        first_reader.join(timeout=3)
        assert not first_reader.is_alive()
        assert [event["path"] for event in first] == ["initial.txt"]

        for number in range(40):
            writer.emit(
                f"file-{number:02d}.txt", number + 1, number + 1, "done",
            )
        assert len(writer.pending) == 40

        received = []

        def read_backlog():
            with status_fifo.open() as stream:
                for _ in range(40):
                    received.append(json.loads(stream.readline()))

        second_reader = threading.Thread(target=read_backlog)
        second_reader.start()
        time.sleep(0.05)
        assert writer.flush_pending()
        second_reader.join(timeout=3)
        writer.close()

        assert not second_reader.is_alive()
        assert [event["path"] for event in received] == [
            f"file-{number:02d}.txt" for number in range(40)
        ]
        assert not writer.pending


def test_unsupported_entries_are_removed_without_following_them():
    processor = load_processor_module()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        outside = root / "outside.txt"
        outside.write_text("must remain")
        link = root / "unsupported-link"
        link.symlink_to(outside)
        fifo = root / "unsupported-fifo"
        os.mkfifo(fifo)
        processor.skip_unsupported_entry(link)
        processor.skip_unsupported_entry(fifo)
        assert not link.exists()
        assert not fifo.exists()
        assert outside.read_text() == "must remain"


def test_tolerate_errors_controls_whether_failure_stops_discovery():
    processor = load_processor_module()
    for tolerate_errors in (False, True):
        result = {"failed": []}
        failed = threading.Event()
        processor.record_worker_failure(
            result, threading.Lock(), "failed.txt", failed, tolerate_errors,
        )
        assert result["failed"] == ["failed.txt"]
        assert failed.is_set() is not tolerate_errors


def test_lstat_if_exists_tolerates_reconciliation_race():
    processor = load_processor_module()
    with tempfile.TemporaryDirectory() as temporary:
        vanished = Path(temporary) / "vanished"
        vanished.write_text("content")
        vanished.unlink()
        assert processor.lstat_if_exists(vanished) is None


def test_allow_and_skip_regex_semantics_and_directory_defaults():
    processor = load_processor_module()
    match_all = processor.re.compile(".*")
    file_allow = processor.re.compile(r".*\.(?:py|txt)")
    file_skip = processor.re.compile(r"(?:^|.*/)test_[^/]+\.py")

    assert processor.path_is_allowed(
        "src/main.py", file_allow, file_skip,
    )
    assert not processor.path_is_allowed(
        "src/test_main.py", file_allow, file_skip,
    )
    assert not processor.path_is_allowed(
        "src/data.json", file_allow, file_skip,
    )

    default_dir_skip = processor.re.compile(processor.DEFAULT_DIR_SKIP_REGEX)
    for path in (
        ".git", "src/.hidden", "src/__pycache__",
        "__pypackages__", "web/node_modules",
    ):
        assert not processor.path_is_allowed(path, match_all, default_dir_skip)
    assert processor.path_is_allowed("src/package", match_all, default_dir_skip)


def test_file_and_directory_filters_control_ingestion(monkeypatch, capsys):
    processor = load_processor_module()

    def fake_nested_upload(
            api_directory, session, worker_id, source, relative, destination,
            metadata, writer, heartbeat, initial_timeout, update_timeout):
        time.sleep(0.2)
        copied = source.stat().st_size
        shutil.copyfile(source, destination / source.name)
        source.unlink()
        return copied

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        request = root / "request"
        stage = request / "input"
        destination = root / "uploads"
        nested_api = root / "streaming-file-upload"
        for path in (
            stage / "keep",
            stage / ".git",
            stage / ".hidden",
            stage / "src" / "__pycache__",
            stage / "web" / "node_modules" / "pkg",
            destination,
            nested_api,
        ):
            path.mkdir(parents=True, exist_ok=True)
        os.mkfifo(request / "status-1")
        (stage / "keep" / "allow.txt").write_text("allowed")
        (stage / "keep" / "skip.tmp").write_text("file skip wins")
        (stage / "keep" / "empty.txt").touch()
        (stage / ".git" / "config.txt").write_text("hidden")
        (stage / ".git" / "config-link").symlink_to("config.txt")
        (stage / ".hidden" / "data.txt").write_text("hidden")
        (stage / "src" / "__pycache__" / "cached.txt").write_text("cache")
        (stage / "web" / "node_modules" / "pkg" / "data.txt").write_text(
            "vendor"
        )
        (stage / "web" / "node_modules" / "latest").symlink_to(
            "pkg", target_is_directory=True,
        )
        monkeypatch.setattr(processor, "nested_upload", fake_nested_upload)
        monkeypatch.setattr(processor, "MAX_FILES", 1)
        monkeypatch.setattr(processor, "MAX_DIRECTORIES", 3)
        monkeypatch.setattr(processor, "MAX_TOTAL_BYTES", len("allowed"))
        monkeypatch.setenv("STREAMING_FILE_UPLOAD_API", str(nested_api))
        processor.stop_event.clear()
        request_arguments = arguments(destination, workers="1")
        allow_index = request_arguments.index("file_allow_regex") + 1
        request_arguments[allow_index] = r".*\.(?:txt|tmp)"
        request_arguments.extend(["file_skip_regex", r".*\.tmp"])

        return_code = processor.process_directory(
            SimpleNamespace(
                request_directory=request, initial_timeout=1, update_timeout=0.05,
            ),
            request_arguments,
        )

        response = json.loads(capsys.readouterr().out)
        assert return_code == 0
        assert response["files_completed"] == "1/1"
        assert response["files_skipped"] == 6
        assert response["directories_completed"] == "3/3"
        assert response["bytes_completed"] == len("allowed")
        assert response["items_skipped"] == 0
        assert response["items_skipped_path"] == []
        final = Path(response["path"])
        assert sorted(
            path.relative_to(final).as_posix() for path in final.rglob("*")
        ) == ["keep", "keep/allow.txt"]


def test_error_response_preserves_aggregate_statistics():
    processor = load_processor_module()
    response = processor.build_response(
        {"request": "metadata"},
        Path("/uploads/tree"),
        {
            "completed": 3,
            "bytes": 42,
            "failed": ["failed.txt"],
            "skipped": 2,
            "unsupported": {"link", "pipe"},
        },
        {"nested", "nested/empty"},
        ValueError("directory ingestion admission limit exceeded"),
    )
    assert response == {
        "error_code": "1",
        "error_description": "directory ingestion admission limit exceeded",
        "metadata": {"request": "metadata"},
        "path": "/uploads/tree",
        "files_completed": "3/4",
        "directories_completed": "2/2",
        "bytes_completed": 42,
        "files_failed": "1/4",
        "files_failed_path": ["failed.txt"],
        "files_skipped": 2,
        "items_skipped": 2,
        "items_skipped_path": ["link", "pipe"],
    }


def test_admission_limit_error_uses_aggregate_response(monkeypatch, capsys):
    processor = load_processor_module()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        request = root / "request"
        stage = request / "input"
        destination = root / "uploads"
        nested_api = root / "streaming-file-upload"
        stage.mkdir(parents=True)
        destination.mkdir()
        nested_api.mkdir()
        (stage / "over-limit.txt").write_text("payload")
        monkeypatch.setattr(processor, "MAX_FILES", 0)
        monkeypatch.setenv("STREAMING_FILE_UPLOAD_API", str(nested_api))
        processor.stop_event.clear()

        return_code = processor.process_directory(
            SimpleNamespace(
                request_directory=request, initial_timeout=1, update_timeout=0.05,
            ),
            arguments(destination, workers="1"),
        )

        response = json.loads(capsys.readouterr().out)
        assert return_code == 1
        assert response["error_code"] == "1"
        assert "ingestion admission limit exceeded" in (
            response["error_description"]
        )
        assert response["files_completed"] == "0/0"
        assert response["directories_completed"] == "0/0"
        assert response["bytes_completed"] == 0
        assert response["files_failed"] == "0/0"
        assert response["files_failed_path"] == []
        assert response["files_skipped"] == 0
        assert response["items_skipped"] == 0
        assert response["items_skipped_path"] == []


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
        "tolerate_errors=true "
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
    destination = Path("/uploads") / session
    deadline = time.monotonic() + 5
    while not destination.is_dir() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert destination.is_dir()
    (destination / "conflict.txt").write_text("existing")
    for number in range(8):
        (staging / f"file-{number}.txt").write_text(f"payload-{number}")
    (staging / "conflict.txt").write_text("must fail without stopping later files")
    (staging / "unsupported-link").symlink_to("file-0.txt")
    os.mkfifo(staging / "unsupported-fifo")
    result = json.loads(wait_for_fifo(Path(report["result"]), timeout=15).read_text())
    for reader in readers:
        reader.join(timeout=3)
        assert not reader.is_alive()
    assert result["error_code"] != "0"
    assert result["files_completed"] == "8/9"
    assert result["files_failed"] == "1/9"
    assert result["files_failed_path"] == ["conflict.txt"]
    destination = Path(result["path"])
    assert len(list(destination.iterdir())) == 9
    assert result["items_skipped"] == 2
    assert result["items_skipped_path"] == [
        "unsupported-fifo", "unsupported-link",
    ]
    done_paths = {
        record["path"] for records in statuses.values() for record in records
        if record["status"] == "done"
    }
    assert done_paths == {f"file-{number}.txt" for number in range(8)}


def test_running_container_copies_near_limit_tree_exactly():
    api = Path(
        "/api/api.pmccabe_collector.restapi.org/file-uploader/"
        "streaming_directory_upload/POST"
    )
    if not Path("/api").is_dir():
        return

    processor = load_processor_module()
    capacity = min(processor.MAX_FILES, processor.MAX_DIRECTORIES)
    # Keep container coverage representative without making it excessively slow.
    near_limit = (capacity - max(1, capacity // 100)) // 6
    assert 0 < near_limit <= processor.MAX_FILES
    assert near_limit <= processor.MAX_DIRECTORIES

    def tree_manifest(tree):
        directories = sorted(
            path.relative_to(tree).as_posix()
            for path in tree.rglob("*")
            if path.is_dir()
        )
        files = {
            path.relative_to(tree).as_posix(): path.read_bytes()
            for path in tree.rglob("*")
            if path.is_file()
        }
        return directories, files

    wait_for_fifo(api / "exec", timeout=30)
    session = f"directory-near-limit-{os.getpid()}-{time.time_ns()}"
    destination = Path("/uploads") / session
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / "source-tree"
        source.mkdir()
        (source / "payload.bin").write_bytes(os.urandom(32))
        for number in range(near_limit - 1):
            directory = source / f"directory-{number:05d}"
            directory.mkdir()
            (directory / "payload.bin").write_bytes(os.urandom(32))
        expected_manifest = tree_manifest(source)
        assert len(expected_manifest[0]) + 1 == near_limit
        assert len(expected_manifest[1]) == near_limit

        (api / "exec").write_text(
            f"SESSION_ID={session} workers={processor.MAX_WORKERS} "
            f"preferred_directory={session} "
            "WaitInitialQueryTimeoutSec=60 WaitQueryUpdateTimeoutSec=1 "
            "WaitResultConsumptionTimeoutSec=900 "
            "StatusHeartbeatIntervalSec=0.1"
        )
        report = json.loads(
            wait_for_fifo(api / f"result.json_{session}").read_text()
        )

        def drain_status(path):
            with Path(path).open() as stream:
                for _ in stream:
                    pass

        readers = [
            threading.Thread(target=drain_status, args=(path,), daemon=True)
            for path in report["status"]
        ]
        for reader in readers:
            reader.start()

        try:
            shutil.copytree(source, Path(report["input"]) / source.name)
            result = json.loads(Path(report["result"]).read_text())
            for reader in readers:
                reader.join(timeout=10)
                assert not reader.is_alive()

            assert result["error_code"] == "0", result
            assert result["files_completed"] == f"{near_limit}/{near_limit}"
            assert result["directories_completed"] == (
                f"{near_limit}/{near_limit}"
            )
            assert result["bytes_completed"] == near_limit * 32
            assert result["files_failed"] == f"0/{near_limit}"
            assert result["files_skipped"] == 0
            assert result["items_skipped"] == 0
            copied_tree = Path(result["path"]) / source.name
            assert tree_manifest(copied_tree) == expected_manifest
        finally:
            shutil.rmtree(destination, ignore_errors=True)
