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
# TODO
rm -f ${WORK_DIR}/test_0_pseudo_fs_api_conformance.py
rm -f ${WORK_DIR}/test_1_inner_api_functionality.py
for s in ${WORK_DIR}/test_*.py; do
    if [ -z ${PYTEST_FILTER} ]; then
        pytest -x -r 'A' -s --verbose ${s}
    else
        pytest -x -r 'A' -s --verbose -k "${PYTEST_FILTER}" ${s}
    fi
    VAL=$?
    if [ $VAL != 0 ]
    then
        RET=$VAL
    fi
    echo "API fs snapshot after test execution: ${s}, result: ${VAL}"
    ls -laR ${SHARED_API_DIR}
done

echo "Final API fs snapshot, result ${RET}:"
ls -laR ${SHARED_API_DIR}

if [ $EXIT_ONCE_DONE == true ]; then exit $RET; fi

echo "wait for termination"
sleep infinity &
wait $!
exit $RET
