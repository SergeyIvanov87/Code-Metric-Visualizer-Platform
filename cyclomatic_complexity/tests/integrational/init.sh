#!/bin/bash

export WORK_DIR=${1}
export INITIAL_PROJECT_LOCATION=${2}
export SHARED_API_DIR=${3}

export PYTHONPATH="${WORK_DIR}:${WORK_DIR}/utils:${WORK_DIR}/utils/modules"
export MODULES="${WORK_DIR}/utils/modules"
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport INITIAL_PROJECT_LOCATION=${INITIAL_PROJECT_LOCATION}\nexport MODULES=${MODULES}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh

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
