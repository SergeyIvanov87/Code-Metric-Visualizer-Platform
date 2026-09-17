from pathlib import Path
import subprocess
import sys


def test_connections_are_combined_by_producer_in_connection_order(tmp_path):
    connections = tmp_path / "connections"
    combined = tmp_path / "combined"
    connections.mkdir()
    (connections / "host-a__connection_116.log").write_bytes(b"third\n")
    (connections / "host-b__connection_8.log").write_bytes(b"other\n")
    (connections / "host-a__connection_9.log").write_bytes(b"first\nsecond\n")
    (connections / "connection_1.log").write_bytes(b"")

    script = Path(__file__).with_name("aggregate_connection_logs.py")
    result = subprocess.run(
        [sys.executable, str(script), str(connections), str(combined)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (combined / "host-a.log").read_bytes() == b"first\nsecond\nthird\n"
    assert (combined / "host-b.log").read_bytes() == b"other\n"
    assert sorted(path.name for path in connections.iterdir()) == [
        "connection_1.log",
        "host-a__connection_116.log",
        "host-a__connection_9.log",
        "host-b__connection_8.log",
    ]
