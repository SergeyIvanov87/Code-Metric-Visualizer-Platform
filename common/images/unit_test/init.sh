#!/bin/bash

export WORK_DIR=${1}
export SHARED_API_DIR=${2}

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org
export PYTHONPATH="${WORK_DIR}:${WORK_DIR}/utils:${WORK_DIR}/utils/modules"
UTILS="${WORK_DIR}/utils"
export MODULES="${WORK_DIR}/utils/modules"

# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh


echo "Run tests:"
RET=0
for s in ${WORK_DIR}/test_*.py; do
    pytest -rxXs ${s}
    VAL=$?
    if [ $VAL != 0 ]
    then
        RET=$VAL
    fi
done

if [ $EXIT_ONCE_DONE == true ]; then exit $RET; fi

echo "wait for termination"
sleep infinity &
wait $!
exit $RET
