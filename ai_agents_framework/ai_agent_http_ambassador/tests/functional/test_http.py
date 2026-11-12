"""Black-box HTTP checks against the Compose-provided ambassador."""

import json
from pathlib import Path
import time
import unittest
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError

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
        for action in ("add_doc", "bulk_add"):
            with self.subTest(action=action), urlopen(BASE + ROOT + f"/{action}/v1") as response:
                self.assertNotIn(b"preserveOriginal", response.read())

    def test_single_upload_stages_file_and_forces_uri_preservation_policy(self):
        for supplied in ({}, {"preserveOriginal": "1"}, {"-preserveOriginal": "1"}):
            query = urlencode({"filename": 'document "with spaces".txt', **supplied})
            request = Request(BASE + ROOT + "/add_doc/v1?" + query, b"hello\r\n",
                              {"Content-Type": "application/octet-stream"}, method="PUT")
            with self.subTest(supplied=supplied), urlopen(request, timeout=10) as response:
                result = json.load(response)
                args = result["arguments"]
                self.assertEqual(args[args.index("-preserveOriginal") + 1], "0")
                self.assertIn("-URI", args)
                self.assertNotIn("--doc_data", args)
                self.assertEqual(result["data"], "hello\n")
                self.assertFalse(Path(result["URI"]).exists())

    def test_bulk_upload_forces_zero_in_filesystem_request(self):
        for supplied in ({}, {"preserveOriginal": "1"}):
            request = Request(BASE + ROOT + "/bulk_add/v1", json.dumps(supplied).encode(),
                              {"Content-Type": "application/json"}, method="POST")
            with self.subTest(supplied=supplied), urlopen(request, timeout=10) as response:
                self.assertEqual(json.load(response)["upload_id"], "deferred-test")
                arguments = json.loads(Path("/api/bulk-arguments.json").read_text())
                self.assertIn("-preserveOriginal=0", arguments)
                self.assertNotIn("-preserveOriginal=1", arguments)

    def test_failed_upload_cleans_up_known_completed_input(self):
        request = Request(BASE + ROOT + "/add_doc/v1?filename=failed.txt", b"failed input",
                          {"Content-Type": "application/octet-stream"}, method="PUT")
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=10)
        self.assertEqual(raised.exception.code, 502)
        result = json.load(raised.exception)
        self.assertFalse(Path(result["URI"]).exists())

    def test_invalid_result_retains_source_for_possible_late_consumption(self):
        request = Request(BASE + ROOT + "/add_doc/v1?filename=bad-result.txt", b"pending input",
                          {"Content-Type": "application/octet-stream"}, method="PUT")
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=10)
        self.assertEqual(raised.exception.code, 502)
        retained = list(Path("/api/.http-document-uploads").glob("*/bad-result.txt"))
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0].read_bytes(), b"pending input")

    def test_upload_filename_cannot_escape_staging(self):
        request = Request(BASE + ROOT + "/add_doc/v1?" + urlencode({"filename": "../escape.txt"}),
                          b"input", {"Content-Type": "application/octet-stream"}, method="PUT")
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=10)
        self.assertEqual(raised.exception.code, 400)
