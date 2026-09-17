import os
from pathlib import Path
import subprocess
import sys
from itertools import permutations


def run_aggregator(tmp_path, log_records):
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
    (logs_dir / "tester.log").write_bytes(log_records)

    script = Path(__file__).with_name("log_aggregator.py")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(stub_dir)
    return subprocess.run(
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


def test_malformed_utf8_log_record_does_not_crash_aggregator(tmp_path):
    result = run_aggregator(
        tmp_path,
        b"<27>Sep 13 19:43:49 tester[1]: collected 1 item\n"
        b"<27>Sep 13 19:43:49 tester[1]: Loading weights: \xe2\n"
        b"<27>Sep 13 19:43:50 tester[1]: ========== 1 passed in 0.01s ==========\n",
    )

    assert result.returncode == 0, result.stderr
    assert "All tests PASSED: (1/1)" in result.stdout
    assert "UnicodeDecodeError" not in result.stderr


def test_pytest_summary_counts_every_combination_of_supported_outcomes(tmp_path):
    outcome_counts = {"passed": 2, "failed": 1, "skipped": 3}
    combinations = [
        order
        for length in range(1, len(outcome_counts) + 1)
        for order in permutations(outcome_counts, length)
    ]

    for case_number, outcomes in enumerate(combinations):
        case_path = tmp_path / str(case_number)
        case_path.mkdir()
        total = sum(outcome_counts[outcome] for outcome in outcomes)
        summary = ", ".join(
            f"{outcome_counts[outcome]} {outcome}" for outcome in outcomes
        )
        # Warnings may follow any combination of test outcomes, but are not
        # tests and must therefore not affect the total.
        summary += ", 4 warnings"
        result = run_aggregator(
            case_path,
            (
                f"<27>Sep 13 19:43:49 tester[1]: collected {total} items\n"
                f"<27>Sep 13 19:43:50 tester[1]: "
                f"========== {summary} in 0.01s ==========\n"
            ).encode(),
        )

        expected = {
            outcome: outcome_counts[outcome] if outcome in outcomes else 0
            for outcome in outcome_counts
        }
        statistic = (
            f'Statistic of "tester" - total: {total}, '
            f'failed: {expected["failed"]}, passed: {expected["passed"]}, '
            f'skipped: {expected["skipped"]}'
        )
        assert statistic in result.stdout
        assert 'Statistic of "tester" is inconsistent' not in result.stderr
        should_succeed = "passed" in outcomes and "failed" not in outcomes
        assert (result.returncode == 0) == should_succeed


def test_multiple_pytest_sessions_use_completed_summaries_for_totals(tmp_path):
    result = run_aggregator(
        tmp_path,
        (
            "<27>Sep 13 19:43:49 tester[1]: collected 2 items\n"
            "<27>Sep 13 19:43:50 tester[1]: ===== 2 passed in 8.00s =====\n"
            # A collection record may be lost when a fragmented TCP/syslog
            # stream is reconstructed; its completed summary is sufficient.
            "<27>Sep 13 19:47:54 tester[1]: ===== 3 passed in 244.06s (0:04:04) =====\n"
        ).encode(),
    )

    assert result.returncode == 0, result.stderr
    assert (
        'Statistic of "tester" - total: 5, failed: 0, passed: 5, skipped: 0'
        in result.stdout
    )
    assert "All tests PASSED: (5/5)" in result.stdout


def test_collection_lines_from_incomplete_sessions_do_not_mix_counters(tmp_path):
    result = run_aggregator(
        tmp_path,
        (
            "<27>Sep 13 19:43:49 tester[1]: collected 5 items\n"
            "<27>Sep 13 19:43:50 tester[1]: ===== 1 skipped in 0.11s =====\n"
            "<27>Sep 13 19:43:51 tester[1]: collected 4 items\n"
            "<27>Sep 13 19:49:00 tester[1]: ===== 2 passed in 377.16s (0:06:17) =====\n"
        ).encode(),
    )

    assert result.returncode == 0, result.stderr
    assert (
        'Statistic of "tester" - total: 3, failed: 0, passed: 2, skipped: 1'
        in result.stdout
    )
    assert 'Statistic of "tester" is inconsistent' not in result.stderr
