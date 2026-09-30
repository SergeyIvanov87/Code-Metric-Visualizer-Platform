import json
import os
from pathlib import Path
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


def test_schema_declares_distinct_shared_staging_query():
    schema = json.loads(SCHEMA.read_text())
    assert schema["Query"] == "+/streaming_directory_events"
    assert schema["Params"]["WaitQueryUpdateTimeoutSec"] == "0.25"
    assert "destination" not in schema["Params"]
    assert "workers" not in schema["Params"]


def test_preflight_creates_input_on_configured_shared_mount():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        request = root / "request"
        staging = root / "shared-staging"
        request.mkdir()
        env = {**os.environ, "FILE_UPLOADER_STAGING_ROOT": str(staging)}
        checked = invoke(request, "--check-arguments", env=env)
        assert checked.returncode == 0, checked.stdout + checked.stderr
        prepared = invoke(request, "--prepare-api-channel", env=env)
        assert prepared.returncode == 0, prepared.stdout + prepared.stderr
        report = json.loads(prepared.stdout)
        input_path = Path(report["input"])
        staging_path = Path(report["staging"])
        assert report["protocol"] == "cmvp.directory-events.v1"
        assert report["input_type"] == "DIRECTORY"
        assert report["staging_type"] == "DIRECTORY"
        assert input_path.is_dir()
        assert input_path.is_symlink()
        assert input_path.parent == request
        assert input_path.resolve() == staging_path
        assert staging_path.parent == staging.resolve()
        assert report["events_type"] == "FIFO"
        assert stat.S_ISFIFO(Path(report["events"]).stat().st_mode)

        (input_path / "survives.txt").write_text("shared content")
        shutil.rmtree(request)
        assert not input_path.exists()
        assert (staging_path / "survives.txt").read_text() == "shared content"


def test_events_fifo_batches_all_events_since_previous_delivery():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        request = root / "request"
        staging = root / "shared-staging"
        request.mkdir()
        env = {**os.environ, "FILE_UPLOADER_STAGING_ROOT": str(staging)}
        prepared = invoke(request, "--prepare-api-channel", env=env)
        assert prepared.returncode == 0, prepared.stdout + prepared.stderr
        input_path = Path(json.loads(prepared.stdout)["input"])
        events_fifo = Path(json.loads(prepared.stdout)["events"])
        assert stat.S_ISFIFO(events_fifo.stat().st_mode)
        process = subprocess.Popen([
            sys.executable, str(PROCESSOR), "--request-directory", str(request),
            "--initial-timeout", "2", "--update-timeout", "0.1",
            "--", *arguments(),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        try:
            for number in range(40):
                temporary_path = input_path / f".{number}.tmp"
                temporary_path.write_text(f"payload {number}")
                temporary_path.rename(input_path / f"file-{number}.txt")
            time.sleep(0.25)
            first = json.loads(events_fifo.read_text())
            assert first["first_sequence"] == 1
            assert first["last_sequence"] == 40
            assert len(first["events"]) == 40
            assert {event["path"] for event in first["events"]} == {
                f"file-{number}.txt" for number in range(40)
            }

            for number in range(40, 43):
                (input_path / f"file-{number}.txt").write_text(f"payload {number}")
            time.sleep(0.25)
            second = json.loads(events_fifo.read_text())
            assert second["first_sequence"] == 41
            assert second["last_sequence"] == 43
            assert len(second["events"]) == 3

            journal = [json.loads(line) for line in
                       (request / "event_journal.jsonl").read_text().splitlines()]
            assert [event["sequence"] for event in journal] == list(range(1, 44))
            assert all(path.exists() for path in input_path.iterdir())
            stdout, stderr = process.communicate(timeout=2)
            assert process.returncode == 0, stdout + stderr
            final = json.loads(stdout)
            assert final == {
                "error_code": "0", "error_description": "",
                "path": str(Path(json.loads(prepared.stdout)["staging"])),
                "events_delivered": 43,
                "last_sequence": 43,
            }
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=3)


def test_unread_events_do_not_keep_common_executor_processor_alive_forever():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        request = root / "request"
        staging = root / "shared-staging"
        request.mkdir()
        env = {**os.environ, "FILE_UPLOADER_STAGING_ROOT": str(staging)}
        prepared = invoke(request, "--prepare-api-channel", env=env)
        input_path = Path(json.loads(prepared.stdout)["input"])
        (input_path / "unread.txt").write_text("payload")
        process = subprocess.run([
            sys.executable, str(PROCESSOR), "--request-directory", str(request),
            "--initial-timeout", "1", "--update-timeout", "0.05",
            "--", *arguments(),
        ], text=True, capture_output=True, timeout=2, env=env)
        assert process.returncode == 1
        final = json.loads(process.stdout)
        assert final["error_code"] == "1"
        assert final["events_delivered"] == 0
        assert final["last_sequence"] == 1
        assert "not consumed" in final["error_description"]


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
        "WaitQueryUpdateTimeoutSec=0.2 WaitResultConsumptionTimeoutSec=2"
    )
    report = json.loads(
        wait_for_fifo(api / f"result.json_{session}").read_text()
    )
    assert report["protocol"] == "cmvp.directory-events.v1"
    assert report["events_type"] == "FIFO"
    input_path = Path(report["input"])
    staging = Path(report["staging"])
    assert input_path.is_symlink()
    assert input_path.resolve() == staging
    assert input_path.is_relative_to(api)
    assert staging.is_relative_to(Path("/staging"))
    try:
        for number in range(40):
            temporary_path = input_path / f".{number}.tmp"
            temporary_path.write_text(f"payload {number}")
            temporary_path.rename(input_path / f"file-{number}.txt")
        batch = json.loads(Path(report["events"]).read_text())
        assert batch["first_sequence"] == 1
        assert batch["last_sequence"] == 40
        assert len(batch["events"]) == 40
        assert not (Path("/uploads") / session).exists()
        assert all((staging / event["path"]).is_file()
                   for event in batch["events"])
        final = json.loads(Path(report["result"]).read_text())
        assert final["error_code"] == "0"
        assert final["events_delivered"] == 40
        assert final["last_sequence"] == 40
    finally:
        # Shared-staging content intentionally survives request cleanup, so the
        # integration client releases its own test data.
        shutil.rmtree(staging, ignore_errors=True)
