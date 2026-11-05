"""Exercise optional trust setup through the tester's init.sh registration."""
import os
from pathlib import Path
import ssl
import subprocess

import pytest


TRUST_VARIABLES = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "PIP_CERT", "CURL_CA_BUNDLE")


@pytest.mark.parametrize("certificate", ["missing", "empty", "provided"])
def test_optional_proxy_ca(certificate, tmp_path):
    helper = Path(os.environ["WORK_DIR"]) / "utils/proxy_ca.sh"
    source = tmp_path / "extra.pem"
    system_bundle = Path("/etc/ssl/certs/ca-certificates.crt")
    if certificate == "empty":
        source.write_bytes(b"")
    elif certificate == "provided":
        source.write_bytes(system_bundle.read_bytes())
    environment = os.environ.copy()
    environment.update({name: "existing-trust-setting" for name in TRUST_VARIABLES})
    result = subprocess.run(
        ["sh", "-ec", '. "$1"; configure_proxy_ca "$2"; '
         'printf "%s\\n" "$SSL_CERT_FILE" "$REQUESTS_CA_BUNDLE" "$PIP_CERT" "$CURL_CA_BUNDLE"',
         "proxy-ca-check", str(helper), str(source)],
        env=environment, text=True, capture_output=True, check=True,
    )
    values = result.stdout.splitlines()
    if certificate != "provided":
        assert values == ["existing-trust-setting"] * len(TRUST_VARIABLES)
    else:
        bundle = Path(values[0])
        try:
            assert values == [str(bundle)] * len(TRUST_VARIABLES)
            assert bundle.read_bytes() == system_bundle.read_bytes() + b"\n" + source.read_bytes()
            ssl.create_default_context(cafile=str(bundle))
        finally:
            bundle.unlink()
