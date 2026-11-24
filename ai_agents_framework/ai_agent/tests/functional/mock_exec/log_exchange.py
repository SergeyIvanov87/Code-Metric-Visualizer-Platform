#!/usr/bin/env python

import json

from datetime import datetime, timezone
from pathlib import Path


LOG_PATH = Path("/api/api.pmccabe_collector.restapi.org/tester_logs")


def log_exchange(query_received, query_matched, answer_sent):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query_received": query_received,
        "query_matched": query_matched,
        "answer_sent": answer_sent,
    }
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(entry, sort_keys=True) + "\n")
