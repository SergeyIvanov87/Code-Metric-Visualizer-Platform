#!/usr/bin/env python3
import sys
from mock_utils.mock_case import run
raise SystemExit(run("read_id.json", sys.argv[1:], plain=True))
