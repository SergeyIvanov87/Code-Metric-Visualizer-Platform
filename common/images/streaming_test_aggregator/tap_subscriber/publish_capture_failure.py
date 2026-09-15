#!/usr/bin/env python3
"""Publish a terminal capture failure when the tap process cannot do so."""

import argparse
import json

from confluent_kafka import Producer

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--brokers", required=True)
parser.add_argument("--topic", required=True)
parser.add_argument("--capture-id", required=True)
parser.add_argument("--error-file", required=True)
args = parser.parse_args()
error = open(args.error_file, encoding="utf-8", errors="replace").read()
producer = Producer({
    "bootstrap.servers": args.brokers,
    "enable.idempotence": True,
    "acks": "all",
})
errors = []
producer.produce(
    args.topic,
    key=args.capture_id.encode(),
    value=json.dumps({
        "schema_version": 1,
        "capture_id": args.capture_id,
        "type": "capture_failed",
        "error": error[-8192:],
    }).encode(),
    on_delivery=lambda error, _message: errors.append(str(error)) if error else None,
)
if producer.flush(30) or errors:
    raise RuntimeError("capture failure event was not delivered")
