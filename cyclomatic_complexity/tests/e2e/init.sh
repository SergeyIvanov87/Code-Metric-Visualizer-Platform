#!/bin/bash

export WORK_DIR=${1}
export INITIAL_PROJECT_LOCATION=${2}
export SHARED_API_DIR=${3}

export UTILS="${WORK_DIR}/utils"

MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

echo "Run tests:"
for s in ${WORK_DIR}/test_*.py; do
    pytest ${s}
done
