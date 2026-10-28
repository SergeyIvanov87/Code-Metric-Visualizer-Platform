#!/bin/bash

export WORK_DIR=/tests
export SHARED_API_DIR=/api
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org
export MODULES=/tests/utils/modules
export PYTHONPATH=/tests:/tests/utils:/tests/utils/modules
export OPT_DIR=/tests/utils

${OPT_DIR}/canonize_internal_api.py /API/deps "${MAIN_SERVICE_NAME}/ai_agent" || exit 255

# The same entrypoint serves production, development, and streaming testers.
if ! timeout "${AI_AGENT_READY_TIMEOUT_SEC:-120}" bash -c '
    source "${OPT_DIR}/shell_utils/init_utils.sh"
    wait_for_unavailable_services "${SHARED_API_DIR}" "${MAIN_SERVICE_NAME}/ai_agent"
'; then
    echo "AI-agent API dependencies did not become ready"
    exit 255
fi

# Dependency reports can respond before the agent has finished publishing its APIs.
if ! timeout "${AI_AGENT_READY_TIMEOUT_SEC:-120}" python - <<'PY'
import json
import os
from pathlib import Path
import time

from api_schema_utils import compose_api_queries_pipe_names

schemas = [*Path('/API').glob('*.json'), *Path('/API/deps').glob('*.json')]
pipes = [Path(pipe) for schema in schemas for pipe in compose_api_queries_pipe_names(
    os.environ['SHARED_API_DIR'], json.loads(schema.read_text())
)]
ready = Path(os.environ['SHARED_API_DIR']) / os.environ['MAIN_SERVICE_NAME'] / 'ai_agent/README-API-STATISTIC.md'
while not (ready.is_file() and all(pipe.is_fifo() for pipe in pipes)):
    time.sleep(0.1)
PY
then
    echo "AI-agent API initialization did not finish"
    exit 255
fi

RET=0
for test_file in "${WORK_DIR}"/test_*.py; do
    pytest -s "${test_file}"
    result=$?
    if [ "${result}" -ne 0 ]; then
        RET=${result}
    fi
done

if [ "${EXIT_ONCE_DONE:-true}" = true ]; then
    exit "${RET}"
fi

sleep infinity &
wait $!
exit "${RET}"
