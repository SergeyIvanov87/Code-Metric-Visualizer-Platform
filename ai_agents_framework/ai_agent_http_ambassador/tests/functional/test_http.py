"""Black-box HTTP checks against the Compose-provided ambassador."""

import json
from pathlib import Path
import time
import unittest
from urllib.request import Request, urlopen

BASE = "http://ambassador:8081"
ROOT = "/api.pmccabe_collector.restapi.org/ai_agent/rag"


class HTTPUploadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        deadline = time.monotonic() + 60
        while True:
            try:
                with urlopen(BASE + "/healthz", timeout=2) as response:
                    if response.status == 200:
                        return
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("Ambassador or its FIFO dependencies did not become ready")
            time.sleep(0.2)

    def test_pages_hide_preservation_control(self):
        for action in ("add_doc_data", "bulk_add"):
            with self.subTest(action=action), urlopen(BASE + ROOT + f"/{action}/v1") as response:
                self.assertNotIn(b"preserveOriginal", response.read())

    def test_inline_upload_uses_data_executor_without_preservation(self):
        for supplied in ({}, {"preserveOriginal": "1"}, {"-preserveOriginal": "1"}):
            payload = {"doc_data": "aGVsbG8=", "doc_type": "txt", **supplied}
            request = Request(BASE + ROOT + "/add_doc_data/v1", json.dumps(payload).encode(),
                              {"Content-Type": "application/json"}, method="PUT")
            with self.subTest(supplied=supplied), urlopen(request, timeout=10) as response:
                result = json.load(response)
                args = result["arguments"]
                self.assertNotIn("--preserveOriginal", args)
                self.assertEqual(args[args.index("--doc_type") + 1], "txt")
                self.assertEqual(result["data"], "aGVsbG8=")

    def test_bulk_upload_forces_zero_in_filesystem_request(self):
        for supplied in ({}, {"preserveOriginal": "1"}):
            request = Request(BASE + ROOT + "/bulk_add/v1", json.dumps(supplied).encode(),
                              {"Content-Type": "application/json"}, method="POST")
            with self.subTest(supplied=supplied), urlopen(request, timeout=10) as response:
                self.assertEqual(json.load(response)["upload_id"], "deferred-test")
                arguments = json.loads(Path("/api/bulk-arguments.json").read_text())
                self.assertIn("preserveOriginal=0", arguments)
                self.assertNotIn("preserveOriginal=1", arguments)
