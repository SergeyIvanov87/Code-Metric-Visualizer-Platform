#!/usr/bin/env python3
"""Record requests instead of running ML inference or a bulk uploader."""

import json
from pathlib import Path
import sys

arguments = sys.argv[1:]
if Path(sys.argv[0]).name == "rag_add.py":
    uri = arguments[arguments.index("-URI") + 1]
    if Path(uri).name == "bad-result.txt":
        print("not-json")
        sys.exit(0)
    result = {"error_code": -1 if Path(uri).name == "failed.txt" else 0,
              "arguments": arguments, "data": Path(uri).read_text(), "URI": uri}
elif arguments[0] == "rag_bulk_add":
    Path("/api/bulk-arguments.json").write_text(json.dumps(arguments[1:]))
    result = {
        "error_code": 0, "input": "/api/deferred-test/input",
        "events": "/api/deferred-test/events", "result": "/api/deferred-test/async_result",
        "protocol": "cmvp.rag-bulk-events.v1",
    }
else:
    result = {"error_code": 0, "response": "stub"}
print(json.dumps(result))
