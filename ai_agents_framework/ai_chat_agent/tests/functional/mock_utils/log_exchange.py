#!/usr/bin/env python3

import json

from datetime import datetime, timezone
from pathlib import Path


LOG_PATH = Path("/api/api.pmccabe_collector.restapi.org/tester_logs")


def log_exchange(session_id, query_name, query_received, query_matched, answer_sent):
    if not session_id:
        raise ValueError(f"SESSION_ID is required for {query_name} exchange logging")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    exchange = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query_received": query_received,
        "query_matched": query_matched,
        "answer_sent": answer_sent,
    }
    entry = {session_id: {query_name: exchange}}
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(entry, sort_keys=True) + "\n")
