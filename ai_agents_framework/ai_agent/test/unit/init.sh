#!/bin/sh
set -eu
exec python3 -m pytest -q \
    /repo/ai_agents_framework/ai_agent/tests/test_fs_api_wrappers.py \
    /repo/ai_agents_framework/ai_agent/tests/test_rag_add_executor.py \
    /repo/ai_agents_framework/ai_agent/tests/test_rag_bulk_add.py \
    /tests/cases
