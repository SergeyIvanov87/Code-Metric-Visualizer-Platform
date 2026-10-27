import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from common.tests.unavailable_api import UnavailableAPI


@pytest.fixture
def endpoint(tmp_path):
    node = tmp_path / "api" / "example.org" / "dependency" / "POST"
    node.mkdir(parents=True)
    for name in ("exec", "result.txt", "result.txt_session"):
        os.mkfifo(node / name)
    return node


def test_checker_reports_masked_dependency_and_preserves_live_pipes(endpoint, tmp_path):
    schema = tmp_path / "schemas" / "dependency"
    schema.mkdir(parents=True)
    (schema / "request.json").write_text(json.dumps({
        "Method": "POST", "Query": "example.org/dependency",
        "Content-Type": "text/plain", "Params": {},
    }))
    identities = {p.name: p.stat().st_ino for p in endpoint.iterdir()}
    # A server may still hold the old request FIFO open during the outage.
    request_fd = os.open(endpoint / "exec", os.O_RDWR | os.O_NONBLOCK)
    try:
        with UnavailableAPI(endpoint, tmp_path):
            os.write(request_fd, b"in-flight request\n")
            assert os.read(request_fd, 1024) == b"in-flight request\n"
            # Existing and newly created session results must survive recovery.
            os.mkfifo(endpoint / "result.txt_late_session")
            late_inode = (endpoint / "result.txt_late_session").stat().st_ino
            common = Path(__file__).parent
            result = subprocess.run(
                [sys.executable, str(common / "check_missing_pseudo_fs_from_schema.py"),
                 str(tmp_path / "api"), "example.org", str(schema.parent)],
                env={**os.environ, "PYTHONPATH": str(common / "modules")},
                capture_output=True, text=True, check=True, timeout=5,
            )
            assert "request" in json.loads(result.stdout)["dependency"]
        for name, inode in identities.items():
            assert (endpoint / name).is_fifo()
            assert (endpoint / name).stat().st_ino == inode
        assert (endpoint / "result.txt_late_session").stat().st_ino == late_inode
        assert not list(tmp_path.glob(".unavailable-*"))
    finally:
        os.close(request_fd)


def test_restores_request_on_query_failure(endpoint, tmp_path):
    inode = (endpoint / "exec").stat().st_ino
    with pytest.raises(RuntimeError, match="query failed"):
        with UnavailableAPI(endpoint, tmp_path):
            raise RuntimeError("query failed")
    assert (endpoint / "exec").is_fifo()
    assert (endpoint / "exec").stat().st_ino == inode
    assert not list(tmp_path.glob(".unavailable-*"))


def test_restores_request_when_mask_creation_fails(endpoint, tmp_path, monkeypatch):
    def fail_touch(*args, **kwargs):
        raise OSError("cannot mask")

    monkeypatch.setattr(Path, "touch", fail_touch)
    with pytest.raises(OSError, match="cannot mask"):
        with UnavailableAPI(endpoint, tmp_path):
            pytest.fail("failed setup must not enter the context")
    assert (endpoint / "exec").is_fifo()
    assert not list(tmp_path.glob(".unavailable-*"))


@pytest.mark.parametrize("parallel", [False, True])
def test_generated_server_completes_inflight_response_and_recovers(tmp_path, monkeypatch, parallel):
    common = Path(__file__).parent
    monkeypatch.syspath_prepend(str(common / "modules"))
    from common import build_api_services
    from api_fs_query import APIQueryInterruptible

    node = tmp_path / "example.org" / "dependency" / "POST"
    node.mkdir(parents=True)
    executor = tmp_path / "dependency_exec.sh"
    executor.write_text('#!/bin/bash\ntouch "$1/unexpected-request"\n')
    executor.chmod(0o755)
    script = tmp_path / "server.sh"
    script.write_text("#!/bin/bash\n" + "".join(build_api_services.generate_cli_server_content(
        "dependency", "example.org/dependency", "POST", "text/plain",
        req_exec_script_root_dir=str(tmp_path),
        parallel_by_session=parallel,
    )))
    query = APIQueryInterruptible([str(node / "exec"), str(node / "result.txt")], False)
    with (tmp_path / "server.log").open("w") as log:
        server = subprocess.Popen(
            ["bash", str(script)], env={**os.environ, "SHARED_API_DIR": str(tmp_path)},
            stdout=log, stderr=log, start_new_session=True,
        )
        try:
            assert query.wait_until_valid(sleep_between_cycles=0.01, max_cycles_count=300)
            assert query.execute(3, "API_KEEP_ALIVE_CHECK=before SESSION_ID=probe")[0]
            result_pipe = node / "result.txt_probe"
            deadline = time.monotonic() + 3
            while not result_pipe.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert result_pipe.is_fifo()
            inode = result_pipe.stat().st_ino
            with UnavailableAPI(node, tmp_path):
                assert not query.is_valid()
                # The response already in progress remains readable during the outage.
                status, result, _ = query.wait_result(3, "probe")
                assert status and result == "before"
                time.sleep(0.25)
                assert not (node.parent / "unexpected-request").exists()
            assert result_pipe.stat().st_ino == inode
            assert query.execute(3, "API_KEEP_ALIVE_CHECK=after SESSION_ID=probe")[0]
            status, result, _ = query.wait_result(3, "probe")
            assert status and result == "after"
        finally:
            os.killpg(server.pid, signal.SIGKILL)
            server.wait(timeout=5)
