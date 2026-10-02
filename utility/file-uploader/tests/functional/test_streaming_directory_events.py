import json
import os
from pathlib import Path
import select
import shutil
import stat
import subprocess
import sys
import tempfile
import time


if Path("/package/streaming_directory_events_processor.py").exists():
    PROCESSOR = Path("/package/streaming_directory_events_processor.py")
    SCHEMA = Path("/package/API/streaming_directory_events.json")
else:
    ROOT = Path(__file__).parents[4]
    PROCESSOR = ROOT / "utility/file-uploader/streaming_directory_events_processor.py"
    SCHEMA = ROOT / "utility/file-uploader/API/streaming_directory_events.json"


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


def test_schema_declares_distinct_shared_staging_query():
    schema = json.loads(SCHEMA.read_text())
    assert schema["Query"] == "+/streaming_directory_events"
    assert schema["Params"]["WaitQueryUpdateTimeoutSec"] == "5"
    assert "EventSessionIdleTimeoutSec" not in schema["Params"]
    assert "destination" not in schema["Params"]
    assert "workers" not in schema["Params"]


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
    assert staging.parent == api / ".staging"
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
        assert all((staging / event["path"]).is_file()
                   for event in batch["events"])
        final = json.loads(Path(report["result"]).read_text())
        assert final["error_code"] == "0"
        assert final["seal_reason"] == "explicit"
        assert final["events_delivered"] == 40
        assert final["last_sequence"] == 41
    finally:
        # Shared-staging content intentionally survives request cleanup, so the
        # integration client releases its own test data.
        shutil.rmtree(staging, ignore_errors=True)
