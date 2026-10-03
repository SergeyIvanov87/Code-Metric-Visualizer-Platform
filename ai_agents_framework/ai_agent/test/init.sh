#!/bin/bash

export WORK_DIR=/tests
export SHARED_API_DIR=/api
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org
export MODULES=/tests/utils/modules
export PYTHONPATH=/tests:/tests/utils:/tests/utils/modules

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
