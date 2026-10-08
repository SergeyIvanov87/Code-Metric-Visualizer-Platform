import json
import os
from pathlib import Path
import subprocess
import sys

import tempfile
import unittest
from unittest.mock import patch

from common import deferred_query_launcher as launcher

sys.path.insert(0, str(Path(__file__).parent / "modules"))
import api_fs_exec_utils


def check_generated_reader_preserves_empty_metadata(tmp_path, contents, override):
    (tmp_path / "0.-metadata").write_text(contents)
    (tmp_path / "1.SESSION_ID").write_text("default")
    script = "\n".join([
        *api_fs_exec_utils.generate_exec_header(),
        *api_fs_exec_utils.generate_api_node_env_init(),
        *api_fs_exec_utils.generate_read_api_fs_args(),
        'printf "%s\\0" "${OVERRIDEN_CMD_ARGS[@]}"',
    ])
    completed = subprocess.run(
        ["bash", "-c", script, "reader", str(tmp_path), override],
        capture_output=True, check=True,
    )
    assert completed.stdout.split(b"\0") == [
        b"-metadata", b"", b"SESSION_ID", b"default", b"",
    ]
    processor = Path(__file__).parents[1] / "ai_agents_framework/ai_agent/sources/rag_bulk_add.py"
    checked = subprocess.run([
        sys.executable, str(processor), "--request-directory", str(tmp_path),
        "--check-arguments", "--",
        *[os.fsdecode(arg) for arg in completed.stdout.split(b"\0")[:-1]],
    ], capture_output=True, text=True, check=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent / "modules")})
    assert json.loads(checked.stdout)["error_code"] == "0"


def check_launcher_directories(tmp_path):

    class Child:
        def poll(self):
            return None

    def spawn(command, **kwargs):
        request = Path(command[command.index("--input") + 1])
        lock = Path(command[command.index("--session-lock") + 1])
        assert request.stat().st_mode & 0o777 == 0o777
        assert lock.stat().st_mode & 0o777 == 0o777
        report = {"input": str(request), "input_type": "DIRECTORY",
                  "result": str(request), "result_type": "DIRECTORY"}
        os.write(kwargs["pass_fds"][0], json.dumps(report).encode() + b"\n")
        return Child()

    previous_umask = os.umask(0o077)
    try:
        with patch.object(launcher, "check_validity_of_processors_arguments"), patch.object(launcher.subprocess, "Popen", spawn):
            assert launcher.main([
            "--api-directory", str(tmp_path), "--processor", sys.executable,
            "--executor", sys.executable, "--", "SESSION_ID", "default",
            "WaitInitialQueryTimeoutSec", "60", "WaitQueryUpdateTimeoutSec", "10",
            "WaitResultConsumptionTimeoutSec", "60",
        ]) == 0
    finally:
        os.umask(previous_umask)


class DeferredQueryRegressionTests(unittest.TestCase):
    def test_empty_metadata(self):
        for contents, override in [("", ""), ("\n", ""), ("default", '-metadata=""')]:
            with self.subTest(contents=contents, override=override), tempfile.TemporaryDirectory() as directory:
                check_generated_reader_preserves_empty_metadata(Path(directory), contents, override)

    def test_shared_directory_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            check_launcher_directories(Path(directory))
