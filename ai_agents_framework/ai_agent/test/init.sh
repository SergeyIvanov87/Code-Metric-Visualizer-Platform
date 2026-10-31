#!/bin/bash

export WORK_DIR=/tests
export SHARED_API_DIR=/api
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org
export MODULES=/tests/utils/modules
export PYTHONPATH=/tests:/tests/utils:/tests/utils/modules
export OPT_DIR=/tests/utils

source "${OPT_DIR}/shell_utils/init_utils.sh"
MICROSERVICE_NAME_TO_TEST=ai_agent
echo -e "Wait for ai_agent starting"
if ! wait_for_unavailable_services "${SHARED_API_DIR}" "${MAIN_SERVICE_NAME}/${MICROSERVICE_NAME_TO_TEST}" "${TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC}"; then
    echo -e "${BRed}ERROR: As required APIs are missing, the service considered as inoperable. Abort${Color_Off}"
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
