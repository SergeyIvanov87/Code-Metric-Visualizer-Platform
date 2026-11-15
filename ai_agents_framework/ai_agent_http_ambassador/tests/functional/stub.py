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
    request = Path(
        "/api/api.pmccabe_collector.restapi.org/ai_agent/rag/bulk_add/v1/"
        "POST/deferred-test"
    )
    staging_root = Path("/api/.staging")
    stage = staging_root / "events-functional"
    uploader_request = Path("/api/uploader-functional")
    request.mkdir(parents=True, exist_ok=True)
    staging_root.mkdir(mode=0o2777, parents=True, exist_ok=True)
    staging_root.chmod(0o2777)
    stage.mkdir(mode=0o2777, exist_ok=True)
    stage.chmod(0o2777)
    uploader_request.mkdir(parents=True, exist_ok=True)
    input_path = request / "input"
    if not input_path.exists():
        input_path.symlink_to(stage)
    (request / "stage.json").write_text(json.dumps({
        "uploader_request": str(uploader_request),
    }))
    result = {
        "error_code": 0, "input": str(input_path),
        "events": str(request / "events"),
        "result": str(request / "async_result"),
        "protocol": "cmvp.rag-bulk-events.v1",
    }
else:
    result = {"error_code": 0, "response": "stub"}
print(json.dumps(result))
