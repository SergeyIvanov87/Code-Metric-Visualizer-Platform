#!/bin/bash

export WORK_DIR=${1}
export PERSISTENT_STORAGE_DIR=${2}
export SHARED_API_DIR=${3}
export PYTHONPATH="${WORK_DIR}:${WORK_DIR}/utils:${WORK_DIR}/utils/modules"

export MODULES="${WORK_DIR}/utils/modules"

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org
echo -e "export WORK_DIR=${WORK_DIR}\nexport PERSISTENT_STORAGE_DIR=${PERSISTENT_STORAGE_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport PYTHONPATH=${PYTHONPATH}\nexport MODULES=${MODULES}\nexport MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME}" > ${WORK_DIR}/env.sh


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

if [ $EXIT_ONCE_DONE == true ]; then exit $RET; fi

echo "wait for termination"
sleep infinity &
wait $!
exit $RET
