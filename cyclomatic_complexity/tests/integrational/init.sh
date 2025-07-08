#!/bin/bash

export WORK_DIR=${1}
export INITIAL_PROJECT_LOCATION=${2}
export SHARED_API_DIR=${3}

export PYTHONPATH="${WORK_DIR}:${WORK_DIR}/utils:${WORK_DIR}/utils/modules"
export MODULES="${WORK_DIR}/utils/modules"
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

export OPT_DIR=${WORK_DIR}/utils
export DEPEND_ON_SERVICES_API_SCHEMA_DIR=/API/deps
# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport INITIAL_PROJECT_LOCATION=${INITIAL_PROJECT_LOCATION}\nexport MODULES=${MODULES}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport OPT_DIR=${OPT_DIR}\export DEPEND_ON_SERVICES_API_SCHEMA_DIR=${DEPEND_ON_SERVICES_API_SCHEMA_DIR}\nnexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh


source ${OPT_DIR}/shell_utils/init_utils.sh



${OPT_DIR}/canonize_internal_api.py ${DEPEND_ON_SERVICES_API_SCHEMA_DIR} ${MAIN_SERVICE_NAME}/cc_integrational_tester
${OPT_DIR}/api_management.py ${DEPEND_ON_SERVICES_API_SCHEMA_DIR} ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} &
API_MANAGEMENT_PID=$!

declare -A SERVICE_WATCH_PIDS
termination_handler(){
    gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}
    exit 0
}
trap "termination_handler" SIGHUP SIGQUIT SIGABRT SIGKILL SIGALRM SIGTERM


# Launch internal API services
${OPT_DIR}/build_common_api_services.py ${DEPEND_ON_SERVICES_API_SCHEMA_DIR} -os ${WORK_DIR}/aux_services -oe ${WORK_DIR}
${OPT_DIR}/build_api_pseudo_fs.py ${DEPEND_ON_SERVICES_API_SCHEMA_DIR} ${SHARED_API_DIR}

launch_fs_api_services SERVICE_WATCH_PIDS "${WORK_DIR}/aux_services"


echo -e "${Blue}Skip checking API dependencies${Color_Off}: ${BBlack}${SKIP_API_DEPS_CHECK}${Color_Off}"
wait_for_unavailable_services ${SHARED_API_DIR} "${MAIN_SERVICE_NAME}/cc_integrational_tester" ANY_SERVICE_UNAVAILABLE_COUNT ${TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC}
if [ ! -z ${ANY_SERVICE_UNAVAILABLE_COUNT} ]; then
    echo -e "${BRed}ERROR: As required APIs are missing, the service considered as inoperable. Abort${Color_Off}"
    gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}
    exit 255
fi

echo "EXCLUDE test_1_inner_api_functionality.py"
rm -f ${WORK_DIR}/test_1_inner_api_functionality.py

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
