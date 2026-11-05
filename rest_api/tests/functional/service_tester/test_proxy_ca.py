"""Exercise the shared trust wrapper through the tester's init.sh."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest


HELPER = "/usr/local/bin/with-proxy-ca.sh"
TRUST_VARIABLES = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "PIP_CERT", "CURL_CA_BUNDLE")


@pytest.mark.parametrize("certificate", ["missing", "empty", "provided"])
@pytest.mark.parametrize("exit_code", [0, 7])
def test_optional_proxy_ca(certificate, exit_code, tmp_path):
    source = tmp_path / "extra.pem"
    if certificate == "empty":
        source.write_bytes(b"")
    elif certificate == "provided":
        source.write_bytes(Path("/etc/ssl/certs/ca-certificates.crt").read_bytes())
    environment = os.environ.copy()
    environment.update({name: "existing-trust-setting" for name in TRUST_VARIABLES})
    environment.update(PROXY_CA_PATH=str(source), TMPDIR=str(tmp_path))
    command = '''
import json, os, pathlib, ssl, sys
assert sys.stdin.read() == "preserved stdin"
values = [os.environ[name] for name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "PIP_CERT", "CURL_CA_BUNDLE")]
if values[0] != "existing-trust-setting":
    bundle = pathlib.Path(values[0])
    assert bundle.read_bytes() == pathlib.Path("/etc/ssl/certs/ca-certificates.crt").read_bytes() + b"\\n" + pathlib.Path(sys.argv[1]).read_bytes()
    ssl.create_default_context(cafile=str(bundle))
print(json.dumps(values))
sys.exit(int(sys.argv[2]))
'''
    result = subprocess.run([HELPER, sys.executable, "-c", command, str(source), str(exit_code)],
                            env=environment, input="preserved stdin", text=True, capture_output=True)
    assert result.returncode == exit_code, result.stderr
    values = json.loads(result.stdout)
    if certificate != "provided":
        assert values == ["existing-trust-setting"] * len(TRUST_VARIABLES)
    else:
        assert values == [values[0]] * len(TRUST_VARIABLES)
        assert not Path(values[0]).exists(), "Temporary CA bundle must be removed"


def test_wrapper_requires_a_command():
    result = subprocess.run([HELPER], capture_output=True, text=True)
    assert result.returncode == 2
    assert "Usage:" in result.stderr


def test_wrapper_forwards_shutdown_and_removes_bundle(tmp_path):
    ready = tmp_path / "ready"
    environment = os.environ.copy()
    environment.update(PROXY_CA_PATH="/etc/ssl/certs/ca-certificates.crt", TMPDIR=str(tmp_path))
    command = 'import os,pathlib,sys,time; pathlib.Path(sys.argv[1]).write_text(os.environ["SSL_CERT_FILE"]); time.sleep(60)'
    process = subprocess.Popen([HELPER, sys.executable, "-c", command, str(ready)], env=environment)
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), "Wrapped process did not become ready"
        bundle = Path(ready.read_text())
        assert bundle.exists()
        process.terminate()
        assert process.wait(timeout=5) == 143
        assert not bundle.exists()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
