#!/bin/bash

export WORK_DIR=${1}
export SHARED_API_DIR=${2}

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org
export PYTHONPATH="${WORK_DIR}:${WORK_DIR}/utils:${WORK_DIR}/utils/modules"
UTILS="${WORK_DIR}/utils"
export MODULES="${WORK_DIR}/utils/modules"

# clear existing generated API schema files to facilitate clear-build environment
rm -fr ${WORK_DIR}/API_for_testing
mkdir -p ${WORK_DIR}/API_for_testing
cp -r ${WORK_DIR}/collected_API/* ${WORK_DIR}/API_for_testing/

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
