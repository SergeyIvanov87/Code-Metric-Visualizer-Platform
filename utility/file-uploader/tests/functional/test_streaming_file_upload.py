import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time


if Path("/opt/deferred_query_launcher.py").exists():
    LAUNCHER = Path("/opt/deferred_query_launcher.py")
    EXECUTOR = Path("/opt/deferred_query_executor.py")
    PROCESSOR = Path("/package/streaming_file_upload_processor.py")
    SCHEMA = Path("/package/API/streaming_file_upload.json")
else:
    ROOT = Path(__file__).parents[4]
    LAUNCHER = ROOT / "common/deferred_query_launcher.py"
    EXECUTOR = ROOT / "common/deferred_query_executor.py"
    PROCESSOR = ROOT / "utility/file-uploader/streaming_file_upload_processor.py"
    SCHEMA = ROOT / "utility/file-uploader/API/streaming_file_upload.json"


def arguments(destination, session="test", initial="1", preferred="binary.dat"):
    return [
        "metadata", "", "preferred_filename", preferred,
        "destination", str(destination),
        "WaitInitialQueryTimeoutSec", initial,
        "WaitQueryUpdateTimeoutSec", "0.15",
        "WaitResultConsumptionTimeoutSec", "1",
        "SESSION_ID", session,
    ]


def launch(api, destination, extra_arguments=None):
    command = [
        sys.executable, str(LAUNCHER), "--api-directory", str(api),
        "--processor", str(PROCESSOR), "--executor", str(EXECUTOR), "--",
        *(extra_arguments or arguments(destination)),
    ]
    return subprocess.run(command, text=True, capture_output=True, timeout=3)


def wait_for_fifo(path, timeout=5):
    """Wait for a FIFO to become visible across the shared container volume."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if stat.S_ISFIFO(path.stat().st_mode):
                return path
        except FileNotFoundError:
            pass
        time.sleep(0.01)
    raise AssertionError(f"FIFO did not appear within {timeout} seconds: {path}")


def test_deferred_upload_validation_timeout_binary_data_and_cleanup():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        api = root / "api"
        destination = root / "uploads"
        api.mkdir()
        destination.mkdir()

        invalid = launch(api, destination, arguments(destination, initial="invalid"))
        assert invalid.returncode != 0
        assert list(api.iterdir()) == []

        invalid_backend_arguments = arguments(destination)
        invalid_backend_arguments[1] = "not-json"
        invalid = launch(api, destination, invalid_backend_arguments)
        assert invalid.returncode != 0
        assert "processor argument validation failed" in invalid.stderr
        assert list(api.iterdir()) == []

        timed_out = launch(api, destination, arguments(destination, session="timeout", initial="0.1"))
        assert timed_out.returncode == 0
        timed_out_directory = Path(timed_out.stdout.strip()).parent
        deadline = time.monotonic() + 2
        while timed_out_directory.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not timed_out_directory.exists()
        assert list(destination.iterdir()) == []

        started = launch(api, destination)
        assert started.returncode == 0, started.stderr
        input_fifo = wait_for_fifo(Path(started.stdout.strip()))
        request_directory = input_fifo.parent
        assert not (request_directory / "upload").exists()

        duplicate = launch(api, destination)
        assert duplicate.returncode != 0

        payload = b"binary\x00payload\n" * 10000
        input_fifo.write_bytes(payload)
        result = json.loads(wait_for_fifo(request_directory / "async_result").read_text())
        assert result["error_code"] == "0"
        assert result["error_description"] == ""
        assert result["metadata"] == {}
        assert (destination / "binary.dat").read_bytes() == payload


def test_schema_uses_relative_query_and_declares_upload_parameters():
    schema = json.loads(SCHEMA.read_text())
    assert schema["Query"] == "+/streaming_file_upload"
    assert {
        "metadata", "preferred_filename", "destination",
        "WaitInitialQueryTimeoutSec", "WaitQueryUpdateTimeoutSec",
        "WaitResultConsumptionTimeoutSec",
    } <= schema["Params"].keys()
    assert schema["Params"]["WaitInitialQueryTimeoutSec"] == "60"
    assert schema["Params"]["WaitResultConsumptionTimeoutSec"] == "60"


def test_processor_accepts_schema_encoded_empty_values():
    with tempfile.TemporaryDirectory() as temporary:
        result = subprocess.run(
            [
                sys.executable, str(PROCESSOR), "--check-arguments",
                "metadata", "\"\"", "preferred_filename", "\"\"",
                "destination", temporary,
            ],
            text=True, capture_output=True, timeout=3,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout)["error_code"] == "0"


def test_check_arguments_text_is_valid_as_a_preferred_filename():
    with tempfile.TemporaryDirectory() as temporary:
        result = subprocess.run(
            [
                sys.executable, str(PROCESSOR), "metadata", "{}",
                "preferred_filename", "--check-arguments",
                "destination", temporary,
            ],
            input=b"content", capture_output=True, timeout=3,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert (Path(temporary) / "--check-arguments").read_bytes() == b"content"


def test_running_container_filesystem_api():
    """Exercise the generated service when this test runs under Compose."""
    api_node = Path("/api/api.pmccabe_collector.restapi.org/file-uploader/streaming_file_upload/POST")
    if not Path("/api").is_dir():
        return
    deadline = time.monotonic() + 30
    while not (api_node / "exec").exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert (api_node / "exec").exists()

    session = f"functional-{os.getpid()}"
    (api_node / "exec").write_text(
        f'SESSION_ID={session} metadata="" preferred_filename=functional.bin '
        "WaitInitialQueryTimeoutSec=5 WaitQueryUpdateTimeoutSec=0.1 "
        "WaitResultConsumptionTimeoutSec=5"
    )
    handshake_fifo = wait_for_fifo(api_node / f"result.json_{session}")
    input_fifo = wait_for_fifo(Path(handshake_fifo.read_text().strip()))
    assert input_fifo.parent.parent == api_node
    assert input_fifo.parent.is_dir()
    payload = b"functional upload\x00\n"
    input_fifo.write_bytes(payload)
    result_fifo = wait_for_fifo(input_fifo.parent / "async_result")
    result = json.loads(result_fifo.read_text())
    assert result["error_code"] == "0"
    assert Path("/uploads/functional.bin").read_bytes() == payload

    # Leave a deferred request active when the tester exits. Docker Compose then
    # stops the uploader, and the workflow's artifact check verifies shutdown
    # removed both FIFOs from this unique request directory.
    shutdown_session = f"shutdown-cleanup-{os.getpid()}"
    (api_node / "exec").write_text(
        f"SESSION_ID={shutdown_session} WaitInitialQueryTimeoutSec=60"
    )
    shutdown_handshake = wait_for_fifo(api_node / f"result.json_{shutdown_session}")
    shutdown_input = wait_for_fifo(Path(shutdown_handshake.read_text().strip()))
    wait_for_fifo(shutdown_input.parent / "async_result")
