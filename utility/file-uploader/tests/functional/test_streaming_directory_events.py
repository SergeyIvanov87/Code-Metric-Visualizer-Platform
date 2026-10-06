import importlib.util
import json
import os
from pathlib import Path
import select
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace


if Path("/package/streaming_directory_events_processor.py").exists():
    PROCESSOR = Path("/package/streaming_directory_events_processor.py")
    SCHEMA = Path("/package/API/streaming_directory_events.json")
else:
    ROOT = Path(__file__).parents[4]
    PROCESSOR = ROOT / "utility/file-uploader/streaming_directory_events_processor.py"
    SCHEMA = ROOT / "utility/file-uploader/API/streaming_directory_events.json"

if Path("/opt/modules/directory_event_protocol.py").exists():
    PROTOCOL_MODULE = Path("/opt/modules/directory_event_protocol.py")
else:
    PROTOCOL_MODULE = Path(__file__).parents[4] / "common/modules/directory_event_protocol.py"
protocol_spec = importlib.util.spec_from_file_location(
    "directory_event_protocol", PROTOCOL_MODULE,
)
protocol_module = importlib.util.module_from_spec(protocol_spec)
protocol_spec.loader.exec_module(protocol_module)
parse_directory_event_stream = protocol_module.parse_directory_event_stream


def arguments(session="events-test"):
    return [
        "file_allow_regex", ".*", "file_skip_regex", r"(?!)",
        "dir_allow_regex", ".*", "dir_skip_regex", r"(?!)",
        "WaitResultConsumptionTimeoutSec", "0.3",
        "SESSION_ID", session,
    ]


def invoke(request, *options, env=None):
    return subprocess.run(
        [sys.executable, str(PROCESSOR), "--request-directory", str(request),
         *options, "--", *arguments()],
        text=True, capture_output=True, timeout=3, env=env,
    )


def load_processor_module():
    spec = importlib.util.spec_from_file_location("events_processor", PROCESSOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wait_for_fifo(path, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if stat.S_ISFIFO(path.stat().st_mode):
                return path
        except FileNotFoundError:
            pass
        time.sleep(0.01)
    raise AssertionError(f"FIFO did not appear: {path}")


class EventReader:
    def __init__(self, path):
        self.descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        self.buffer = bytearray()

    def next(self, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line, separator, remainder = self.buffer.partition(b"\n")
            if separator:
                self.buffer = bytearray(remainder)
                return json.loads(line)
            ready, _, _ = select.select([self.descriptor], [], [], 0.05)
            if ready:
                chunk = os.read(self.descriptor, 65536)
                if chunk:
                    self.buffer.extend(chunk)
                else:
                    time.sleep(0.01)
        raise AssertionError("timed out waiting for an events record")

    def close(self):
        os.close(self.descriptor)


def assert_delivered_files_exist(staging, events):
    assert events
    assert all((staging / event["path"]).is_file() for event in events)


def test_schema_declares_distinct_shared_staging_query():
    schema = json.loads(SCHEMA.read_text())
    processor = load_processor_module()
    assert schema["Query"] == "+/streaming_directory_events"
    assert schema["Params"] == processor.QUERY_PARAMETER_DEFAULTS
    assert schema["Params"]["WaitQueryUpdateTimeoutSec"] == "10"
    assert "EventSessionIdleTimeoutSec" not in schema["Params"]
    assert "destination" not in schema["Params"]
    assert "workers" not in schema["Params"]


def test_preflight_rejects_unknown_and_unpaired_query_parameters():
    with tempfile.TemporaryDirectory() as temporary:
        request = Path(temporary)
        command = [
            sys.executable, str(PROCESSOR), "--request-directory", str(request),
            "--check-arguments", "--", "unknown_parameter", "value",
        ]
        rejected = subprocess.run(command, text=True, capture_output=True, timeout=3)
        assert rejected.returncode == 1
        assert "unsupported query parameters: unknown_parameter" in rejected.stdout
        command.pop()
        unpaired = subprocess.run(command, text=True, capture_output=True, timeout=3)
        assert unpaired.returncode == 1
        assert "name/value pairs" in unpaired.stdout


def test_preflight_creates_portable_input_link_on_shared_api_volume():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        api = root / "container-api"
        request = api / "POST" / "request"
        request.mkdir(parents=True)
        checked = invoke(request, "--check-arguments")
        assert checked.returncode == 0, checked.stdout + checked.stderr
        prepared = invoke(request, "--prepare-api-channel")
        assert prepared.returncode == 0, prepared.stdout + prepared.stderr
        report = json.loads(prepared.stdout)
        input_path = Path(report["input"])
        staging_path = Path(report["staging"])
        assert report["protocol"] == "cmvp.directory-events.v1"
        assert report["input_type"] == "DIRECTORY"
        assert report["staging_type"] == "DIRECTORY"
        assert input_path.is_dir()
        assert input_path.is_symlink()
        assert not Path(os.readlink(input_path)).is_absolute()
        assert input_path.parent == request
        assert input_path.resolve() == staging_path
        assert staging_path.parent == request.parent / ".staging"
        assert report["events_type"] == "FIFO"
        assert stat.S_ISFIFO(Path(report["events"]).stat().st_mode)
        assert report["seal_type"] == "FIFO"
        assert stat.S_ISFIFO(Path(report["seal"]).stat().st_mode)

        host_api = root / "host-api-mount"
        host_api.symlink_to(api, target_is_directory=True)
        host_input = host_api / "POST" / "request" / "input"
        (host_input / "host-visible.txt").write_text("host view")
        assert (staging_path / "host-visible.txt").read_text() == "host view"

        (input_path / "survives.txt").write_text("shared content")
        shutil.rmtree(request)
        assert not input_path.exists()
        assert (staging_path / "survives.txt").read_text() == "shared content"


def test_scan_enforces_documented_directory_admission_limit():
    processor = load_processor_module()
    patterns, _ = processor.validate(arguments())
    with tempfile.TemporaryDirectory() as temporary:
        stage = Path(temporary)
        (stage / "one").mkdir()
        (stage / "two").mkdir()
        original_limit = processor.MAX_DIRECTORIES
        processor.MAX_DIRECTORIES = 1
        try:
            try:
                processor.scan(stage, patterns, set())
            except ValueError as error:
                assert "directory admission limit" in str(error)
            else:
                raise AssertionError("directory admission limit was not enforced")
        finally:
            processor.MAX_DIRECTORIES = original_limit


def test_events_fifo_streams_immediately_and_explicit_seal_terminates_it():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        request = root / "request"
        request.mkdir()
        prepared = invoke(request, "--prepare-api-channel")
        assert prepared.returncode == 0, prepared.stdout + prepared.stderr
        input_path = Path(json.loads(prepared.stdout)["input"])
        events_fifo = Path(json.loads(prepared.stdout)["events"])
        seal_fifo = Path(json.loads(prepared.stdout)["seal"])
        assert stat.S_ISFIFO(events_fifo.stat().st_mode)
        process = subprocess.Popen([
            sys.executable, str(PROCESSOR), "--request-directory", str(request),
            "--initial-timeout", "2", "--update-timeout", "1",
            "--", *arguments(),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for number in range(40):
                temporary_path = input_path / f".{number}.tmp"
                temporary_path.write_text(f"payload {number}")
                temporary_path.rename(input_path / f"file-{number}.txt")
            time.sleep(0.2)
            reader = EventReader(events_fifo)
            ready_events = []
            while len(ready_events) < 40:
                ready_events.extend(reader.next()["events"])
            assert {event["path"] for event in ready_events} == {
                f"file-{number}.txt" for number in range(40)
            }
            assert_delivered_files_exist(
                Path(json.loads(prepared.stdout)["staging"]), ready_events,
            )

            for number in range(40, 43):
                (input_path / f"file-{number}.txt").write_text(f"payload {number}")
            while len(ready_events) < 43:
                ready_events.extend(reader.next()["events"])
            seal_fifo.write_text("seal\n")
            terminal_batch = reader.next()
            assert terminal_batch["events"][-1]["status"] == "terminated"
            assert terminal_batch["events"][-1]["reason"] == "explicit"
            reader.close()

            journal = [json.loads(line) for line in
                       (request / "event_journal.jsonl").read_text().splitlines()]
            assert [event["sequence"] for event in journal] == list(range(1, 45))
            assert all(path.exists() for path in input_path.iterdir())
            stdout, stderr = process.communicate(timeout=2)
            assert process.returncode == 0, stdout + stderr
            final = json.loads(stdout)
            assert final == {
                "error_code": "0", "error_description": "",
                "path": str(Path(json.loads(prepared.stdout)["staging"])),
                "seal_reason": "explicit", "events_generated": 43,
                "events_delivered": 43, "events_undelivered": 0,
                "termination_event_delivered": True, "last_sequence": 44,
            }
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=3)


def test_explicit_seal_forces_a_post_seal_reconciliation(monkeypatch, capsys):
    processor = load_processor_module()
    with tempfile.TemporaryDirectory() as temporary:
        request = Path(temporary) / "request"
        request.mkdir()
        report = processor.prepare(request, arguments())
        (request / "stage.json").write_text(json.dumps(report))
        reader = EventReader(report["events"])
        identity = (1, 2, 7, 3)
        scans = iter([
            ({}, set(), False),
            ({"last.txt": identity}, {"last.txt"}, True),
            ({"last.txt": identity}, {"last.txt"}, False),
        ])
        monkeypatch.setattr(processor, "scan", lambda *_: next(scans))
        seal_checks = iter([True, False, False])
        monkeypatch.setattr(
            processor, "seal_requested", lambda *_: next(seal_checks),
        )

        try:
            result = processor.run(SimpleNamespace(
                request_directory=request, initial_timeout=1, update_timeout=10,
            ), arguments())
        finally:
            reader.close()

        assert result == 0
        journal = [
            json.loads(line)
            for line in (request / "event_journal.jsonl").read_text().splitlines()
        ]
        assert [event["status"] for event in journal] == ["ready", "terminated"]
        assert journal[0]["path"] == "last.txt"
        assert json.loads(capsys.readouterr().out)["events_generated"] == 1


def test_unread_events_do_not_prevent_idle_sealing():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        request = root / "request"
        request.mkdir()
        prepared = invoke(request, "--prepare-api-channel")
        input_path = Path(json.loads(prepared.stdout)["input"])
        (input_path / "unread.txt").write_text("payload")
        process = subprocess.run([
            sys.executable, str(PROCESSOR), "--request-directory", str(request),
            "--initial-timeout", "1", "--update-timeout", "0.05",
            "--", *arguments(),
        ], text=True, capture_output=True, timeout=3)
        assert process.returncode == 0
        final = json.loads(process.stdout)
        assert final["error_code"] == "0"
        assert final["seal_reason"] == "idle timeout"
        assert final["events_generated"] == 1
        assert final["events_delivered"] == 0
        assert final["events_undelivered"] == 1
        assert final["last_sequence"] == 2


def test_new_forbidden_entities_keep_the_session_active():
    with tempfile.TemporaryDirectory() as temporary:
        request = Path(temporary) / "request"
        request.mkdir()
        prepared = invoke(request, "--prepare-api-channel")
        report = json.loads(prepared.stdout)
        input_path = Path(report["input"])
        process = subprocess.Popen([
            sys.executable, str(PROCESSOR), "--request-directory", str(request),
            "--initial-timeout", "1", "--update-timeout", "0.15",
            "--", *arguments(),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        reader = EventReader(report["events"])
        try:
            for number in range(5):
                (input_path / f"forbidden-{number}").symlink_to("missing")
                time.sleep(0.1)
                assert process.poll() is None
            (input_path / "accepted.txt").write_text("payload")
            ready = reader.next()
            assert ready["events"][0]["path"] == "accepted.txt"
            Path(report["seal"]).write_text("seal\n")
            assert reader.next()["events"][-1]["status"] == "terminated"
            stdout, stderr = process.communicate(timeout=2)
            assert process.returncode == 0, stdout + stderr
        finally:
            reader.close()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=2)


def test_running_container_delivers_forty_events_without_copying_to_uploads():
    api = Path(
        "/api/api.pmccabe_collector.restapi.org/file-uploader/"
        "streaming_directory_events/POST"
    )
    if not Path("/api").is_dir():
        return
    wait_for_fifo(api / "exec", timeout=30)
    session = f"directory-events-{os.getpid()}-{time.time_ns()}"
    (api / "exec").write_text(
        f"SESSION_ID={session} WaitInitialQueryTimeoutSec=5 "
        "WaitQueryUpdateTimeoutSec=5 "
        "WaitResultConsumptionTimeoutSec=2"
    )
    report = json.loads(
        wait_for_fifo(api / f"result.json_{session}").read_text()
    )
    assert report["protocol"] == "cmvp.directory-events.v1"
    assert report["events_type"] == "FIFO"
    assert report["seal_type"] == "FIFO"
    input_path = Path(report["input"])
    staging = Path(report["staging"])
    assert input_path.is_symlink()
    assert input_path.resolve() == staging
    assert input_path.is_relative_to(api)
    assert staging.parent == Path("/staging")
    assert not Path(os.readlink(input_path)).is_absolute()
    try:
        for number in range(40):
            temporary_path = input_path / f".{number}.tmp"
            temporary_path.write_text(f"payload {number}")
            temporary_path.rename(input_path / f"file-{number}.txt")
        reader = EventReader(report["events"])
        delivered = []
        while len(delivered) < 40:
            delivered.extend(reader.next()["events"])
        Path(report["seal"]).write_text("seal\n")
        assert reader.next()["events"][-1]["status"] == "terminated"
        reader.close()
        assert not (Path("/uploads") / session).exists()
        assert_delivered_files_exist(staging, delivered)
        final = json.loads(Path(report["result"]).read_text())
        assert final["error_code"] == "0"
        assert final["seal_reason"] == "explicit"
        assert final["events_delivered"] == 40
        assert final["last_sequence"] == 41
    finally:
        # Shared-staging content intentionally survives request cleanup, so the
        # integration client releases its own test data.
        shutil.rmtree(staging, ignore_errors=True)


def test_running_container_streams_every_file_from_near_limit_tree():
    api = Path(
        "/api/api.pmccabe_collector.restapi.org/file-uploader/"
        "streaming_directory_events/POST"
    )
    if not Path("/api").is_dir():
        return

    processor = load_processor_module()
    capacity = min(processor.MAX_FILES, processor.MAX_DIRECTORIES)
    near_limit = (
        capacity - max(1, capacity // 100)
    ) // 6
    assert 0 < near_limit <= processor.MAX_FILES
    assert near_limit <= processor.MAX_DIRECTORIES
    wait_for_fifo(api / "exec", timeout=30)
    session = f"directory-events-near-limit-{os.getpid()}-{time.time_ns()}"

    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / "source-tree"
        source.mkdir()
        (source / "payload.bin").write_bytes(os.urandom(32))
        for number in range(near_limit - 1):
            directory = source / f"directory-{number:05d}"
            directory.mkdir()
            (directory / "payload.bin").write_bytes(os.urandom(32))
        expected_paths = {
            f"{source.name}/{path.relative_to(source).as_posix()}"
            for path in source.rglob("*") if path.is_file()
        }
        assert len(expected_paths) == near_limit

        (api / "exec").write_text(
            f"SESSION_ID={session} WaitInitialQueryTimeoutSec=60 "
            "WaitQueryUpdateTimeoutSec=10 "
            "WaitResultConsumptionTimeoutSec=900"
        )
        report = json.loads(
            wait_for_fifo(api / f"result.json_{session}").read_text()
        )
        staging = Path(report["staging"])
        parsed_events = []
        reader_errors = []
        reader_ready = threading.Event()

        def consume_events():
            try:
                with Path(report["events"]).open("rb", buffering=0) as stream:
                    reader_ready.set()
                    parsed_events.extend(parse_directory_event_stream(stream))
            except BaseException as error:
                reader_errors.append(error)
                reader_ready.set()

        reader = threading.Thread(target=consume_events, daemon=True)
        reader.start()
        try:
            assert reader_ready.wait(timeout=10)
            assert not reader_errors
            shutil.copytree(source, Path(report["input"]) / source.name)
            Path(report["seal"]).write_text("seal\n")
            reader.join(timeout=180)
            assert not reader.is_alive()
            assert not reader_errors

            ready_events = [
                event for event in parsed_events if event.get("status") == "ready"
            ]
            assert len(ready_events) == near_limit
            assert {event["path"] for event in ready_events} == expected_paths
            assert parsed_events[-1]["status"] == "terminated"

            result = json.loads(Path(report["result"]).read_text())
            assert result["error_code"] == "0", result
            assert result["events_generated"] == near_limit
            assert result["events_delivered"] == near_limit
            assert result["events_undelivered"] == 0
        finally:
            shutil.rmtree(staging, ignore_errors=True)
