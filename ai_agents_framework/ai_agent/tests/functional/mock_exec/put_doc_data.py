#!/usr/bin/env python3
import sys
from mock_utils.mock_case import run
raise SystemExit(run("put_doc_data.json", sys.argv[1:], {"doc_data": sys.stdin.read()}))
