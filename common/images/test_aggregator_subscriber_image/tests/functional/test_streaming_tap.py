from pathlib import Path

LOGS = Path("/logs")


def test_subscriber_persisted_per_connection_taps():
    taps = list((LOGS / "taps").glob("connection_*.pb"))
    assert len(taps) >= 3
    assert all(path.stat().st_size for path in taps)


def test_subscriber_reconstructed_each_tester_stream():
    decoded = LOGS / "syslog-streams"
    assert list(decoded.glob("*passed-tester*"))
    assert list(decoded.glob("*skipped-tester*"))
    assert list(decoded.glob("*mixed-tester*"))


def test_canonical_aggregation_result_is_successful():
    result = LOGS / "aggregator"
    assert (result / "result").read_text().strip() == "0"
    stdout = (result / "result_log_stdout").read_text()
    assert "All tests PASSED: (5/6)" in stdout
    stderr = (result / "result_log_stderr").read_text()
    assert "SKIPPED tests" in stderr
