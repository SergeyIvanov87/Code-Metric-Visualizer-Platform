import base64
import json
from pathlib import Path
import subprocess
import sys


def streamed_read_document(chunk):
    return {
        "socket_streamed_trace_segment": {
            "trace_id": "1",
            "event": {
                "read": {
                    "data": {
                        "as_bytes": base64.b64encode(chunk).decode("ascii"),
                    }
                }
            },
        }
    }


def run_decoder(tmp_path, chunks, *, name_by_producer=False):
    tap_file = tmp_path / "connection_1.json"
    output_file = tmp_path / "connection_1.log"
    tap_file.write_text(
        "".join(json.dumps(streamed_read_document(chunk)) for chunk in chunks),
        encoding="utf-8",
    )

    script = Path(__file__).with_name("decode_envoy_tap.py")
    command = [sys.executable, str(script), str(tap_file), str(output_file)]
    if name_by_producer:
        command.append("--name-by-producer")

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )
    return result, output_file


def test_decoder_reassembles_chunks_before_framing_syslog(tmp_path):
    first = (
        b"<30>Sep 14 11:13:13 host service-tester[7]: collected 2 items"
    )
    second = (
        b"<30>Sep 14 11:13:14 host service-tester[7]: "
        b"================ 2 passed in 0.01s ================"
    )
    joined = first + second

    # Split one header across reads and coalesce the end of one record with the
    # start of the next. These are both legal outcomes for a TCP byte stream.
    result, output_file = run_decoder(
        tmp_path,
        [joined[:3], joined[3:71], joined[71:]],
    )

    assert result.returncode == 0, result.stderr
    assert output_file.read_bytes() == first + b"\n" + second + b"\n"


def test_decoder_names_output_from_docker_syslog_tag(tmp_path):
    first = b"<30>Sep 14 11:13:13 rrd-service[7]: Runlevel change"
    second = b"<30>Sep 14 11:13:14 rrd-service[7]: WARNING cleanup"
    result, output_file = run_decoder(
        tmp_path,
        [first + second],
        name_by_producer=True,
    )

    renamed_output = tmp_path / "rrd-service__connection_1.log"
    assert result.returncode == 0, result.stderr
    assert not output_file.exists()
    assert renamed_output.read_bytes() == first + b"\n" + second + b"\n"


def test_decoder_ignores_non_tester_health_check_connection(tmp_path):
    result, output_file = run_decoder(
        tmp_path,
        [b"75 <13>1 2026-09-14T11:13:13Z host root - - - Hello"],
    )

    assert result.returncode == 0, result.stderr
    assert output_file.read_bytes() == b""


def test_decoder_rejects_unrecognizable_tester_stream(tmp_path):
    result, output_file = run_decoder(tmp_path, [b"broken service-tester output"])

    assert result.returncode != 0
    assert "tester data contains no recognizable" in result.stderr
    assert not output_file.exists()
