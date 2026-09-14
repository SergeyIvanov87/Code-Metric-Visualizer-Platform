import os
from pathlib import Path
import subprocess
import sys


def test_malformed_utf8_log_record_does_not_crash_aggregator(tmp_path):
    stub_dir = tmp_path / "stubs"
    stub_dir.mkdir()
    (stub_dir / "pyinotify.py").write_text(
        """\
IN_DELETE = IN_CREATE = IN_MODIFY = 1
class ProcessEvent: pass
class WatchManager:
    def add_watch(self, *args, **kwargs): return {}
class Notifier:
    def __init__(self, *args, **kwargs): pass
    def process_events(self): pass
    def check_events(self): return False
    def read_events(self): pass
"""
    )

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "tester.log").write_bytes(
        b"<27>Sep 13 19:43:49 tester[1]: collected 1 item\n"
        b"<27>Sep 13 19:43:49 tester[1]: Loading weights: \xe2\n"
        b"<27>Sep 13 19:43:50 tester[1]: ========== 1 passed in 0.01s ==========\n"
    )

    script = Path(__file__).with_name("log_aggregator.py")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(stub_dir)
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            str(logs_dir),
            r"^.*\s.*\s(.*tester.*)\[\d+\]:.*$",
            "-t=20",
            "-f=pcap",
        ],
        capture_output=True,
        text=True,
        env=environment,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr
    assert "All tests PASSED: (1/1)" in result.stdout
    assert "UnicodeDecodeError" not in result.stderr
