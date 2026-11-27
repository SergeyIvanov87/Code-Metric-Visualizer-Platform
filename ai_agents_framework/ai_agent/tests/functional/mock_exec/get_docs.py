#!/usr/bin/env python3
import sys
from mock_utils.mock_case import run
raise SystemExit(run("get_docs.json", sys.argv[1:]))
