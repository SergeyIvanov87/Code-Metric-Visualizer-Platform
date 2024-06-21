#!/bin/bash

export WORK_DIR=${1}
export INITIAL_PROJECT_LOCATION=${2}
export SHARED_API_DIR=${3}
export PYTHONPATH="${WORK_DIR}:${WORK_DIR}/utils:${WORK_DIR}/utils/modules"

export MODULES="${WORK_DIR}/utils/modules"

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

# inject test files into project directory
test_files=(/package/test_data/*.cpp)
for f in ${test_files[@]}; do
    cp ${f} /mnt/
done

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

# remove test files from project directory
for f in ${test_files[@]}; do
     fname=`basename ${f}`
     rm -f /mnt/${fname}
done

if [ $EXIT_ONCE_DONE == true ]; then exit $RET; fi

echo "wait for termination"
sleep infinity &
wait $!
exit $RET
