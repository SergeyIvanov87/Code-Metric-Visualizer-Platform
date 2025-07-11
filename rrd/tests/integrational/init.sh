#!/bin/bash

export WORK_DIR=${1}
export INITIAL_PROJECT_LOCATION=${2}
export SHARED_API_DIR=${3}

export PYTHONPATH="${WORK_DIR}:${WORK_DIR}/utils:${WORK_DIR}/utils/modules"
UTILS="${WORK_DIR}/utils"
export MODULES="${WORK_DIR}/utils/modules"

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org
export OPT_DIR=${WORK_DIR}/utils
export DEPEND_ON_SERVICES_API_SCHEMA_DIR=/API/deps

# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport INITIAL_PROJECT_LOCATION=${INITIAL_PROJECT_LOCATION}\nexport MODULES=${MODULES}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport OPT_DIR=${OPT_DIR}\nexport DEPEND_ON_SERVICES_API_SCHEMA_DIR=${DEPEND_ON_SERVICES_API_SCHEMA_DIR}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh

source ${OPT_DIR}/shell_utils/color_codes.sh
if [ -z ${MICROSERVICE_NAME} ]; then
    echo -e "{BRed}ERROR: Please specify env/arg MICROSERVICE_NAME. Abort${Color_Off}"
    exit 255
fi
echo -e "${BGreen}Initializing: ${MICROSERVICE_NAME}...${Color_Off}"

# prepare gracefull termination handle
source ${OPT_DIR}/shell_utils/init_utils.sh
API_MANAGEMENT_PID=0
declare -A SERVICE_WATCH_PIDS
termination_handler(){
    gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}
    exit 0
}
trap "termination_handler" SIGHUP SIGQUIT SIGABRT SIGKILL SIGALRM SIGTERM


# Launch command API services & gracefull shutdown management process
launch_command_api_services SERVICE_WATCH_PIDS ${DEPEND_ON_SERVICES_API_SCHEMA_DIR} ${WORK_DIR} ${SHARED_API_DIR} "${MAIN_SERVICE_NAME}/${MICROSERVICE_NAME}"
${OPT_DIR}/api_management.py ${DEPEND_ON_SERVICES_API_SCHEMA_DIR} ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} &
API_MANAGEMENT_PID=$!

# Wait until testable service started
echo -e "${Blue}Waiting for API dependencies${Color_Off}"
wait_for_unavailable_services ${SHARED_API_DIR} "${MAIN_SERVICE_NAME}/${MICROSERVICE_NAME}" ANY_SERVICE_UNAVAILABLE_COUNT ${TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC}
if [ ! -z ${ANY_SERVICE_UNAVAILABLE_COUNT} ]; then
    echo -e "${BRed}ERROR: As required APIs are missing, the service considered as inoperable. Abort${Color_Off}"
    gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}
    exit 255
fi


echo "Run tests:"
RET=0
echo "EXCLUDE test_1_inner_api_functionality.py"
rm -f ${WORK_DIR}/test_1_inner_api_functionality.py
for s in ${WORK_DIR}/test_*.py; do
    pytest -s ${s}
    VAL=$?
    if [ $VAL != 0 ]
    then
        RET=$VAL
    fi
done

echo "stop services"
gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}

echo "wait for termination"
sleep infinity &
wait $!
exit $RET
