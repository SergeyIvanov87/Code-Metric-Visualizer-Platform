#!/bin/bash

export WORK_DIR=${1}
export INITIAL_PROJECT_LOCATION=${2}
export SHARED_API_DIR=${3}

export PYTHONPATH="${WORK_DIR}:${WORK_DIR}/utils:${WORK_DIR}/utils/modules"
UTILS="${WORK_DIR}/utils"
export MODULES="${WORK_DIR}/utils/modules"

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

${UTILS}/canonize_internal_api.py /API/deps ${MAIN_SERVICE_NAME}/rrd

echo "Run tests:"
RET=0
for s in ${WORK_DIR}/test_*.py; do
    pytest -s ${s}
    VAL=$?
    if [ $VAL != 0 ]
    then
        RET=$VAL
    fi
done

echo "wait for termination"
sleep infinity &
wait $!
exit $RET
