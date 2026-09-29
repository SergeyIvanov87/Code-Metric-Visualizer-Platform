import json
import os
from pathlib import Path
import sys
import tempfile
import threading

from common import deferred_query_executor as executor


def test_run_processor_captures_result_larger_than_pipe_buf():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        result_path = root / "processor_result"
        payload_size = os.pathconf(root, "PC_PIPE_BUF") * 3
        executor.stopping = False

        complete = executor.run_processor(
            [
                sys.executable,
                "-c",
                f"import sys; sys.stdout.write('x' * {payload_size})",
            ],
            result_path,
        )

        assert complete
        assert result_path.read_bytes() == b"x" * payload_size


def test_run_processor_replaces_output_beyond_configured_limit_with_json():
    with tempfile.TemporaryDirectory() as temporary:
        result_path = Path(temporary) / "processor_result"
        executor.stopping = False

        complete = executor.run_processor(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.write('x' * 2048)",
            ],
            result_path,
            max_result_bytes=1024,
        )

        assert complete
        report = json.loads(result_path.read_text())
        assert report["error_code"] == "1"
        assert "configured result limit (1024 bytes)" in report["error_description"]


def test_publish_streams_payload_larger_than_pipe_buf():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        result_fifo = root / "async_result"
        result_path = root / "processor_result"
        os.mkfifo(result_fifo)
        payload = b"aggregated-result-" * 2048
        assert len(payload) > os.pathconf(result_fifo, "PC_PIPE_BUF")
        result_path.write_bytes(payload)
        received = []
        executor.stopping = False

        reader = threading.Thread(
            target=lambda: received.append(result_fifo.read_bytes())
        )
        reader.start()
        assert executor.publish(result_fifo, result_path, timeout=2)
        reader.join(timeout=2)

        assert not reader.is_alive()
        assert received == [payload]
