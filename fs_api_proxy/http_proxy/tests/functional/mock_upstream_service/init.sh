#!/bin/bash

export WORK_DIR=${1}
export SHARED_API_DIR=${2}
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

export PYTHONPATH="${WORK_DIR}:${WORK_DIR}/utils:${WORK_DIR}/utils/modules"
UTILS="${WORK_DIR}/utils"
export OPT_DIR="${WORK_DIR}/utils"
export MODULES="${WORK_DIR}/utils/modules"

export DEPEND_ON_SERVICES_API_SCHEMA_DIR=/package/API/deps
export DEPEND_ON_UNAVAILABLE_SERVICES_API_SCHEMA_DIR=/package/API/deps_unreachable
export INNER_API_SCHEMA_DIR=/package/API

echo -e "export WORK_DIR=${WORK_DIR}\nexport UTILS=${UTILS}\nexport OPT_DIR=${OPT_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME}\nexport UPSTREAM_SERVICE=${UPSTREAM_SERVICE}\nexport INNER_API_SCHEMA_DIR=${INNER_API_SCHEMA_DIR}\nexport DEPEND_ON_SERVICES_API_SCHEMA_DIR=${DEPEND_ON_SERVICES_API_SCHEMA_DIR}\nexport DEPEND_ON_UNAVAILABLE_SERVICES_API_SCHEMA_DIR=${DEPEND_ON_UNAVAILABLE_SERVICES_API_SCHEMA_DIR}\nDOWNSTREAM_SERVICE_NETWORK_ADDR=${DOWNSTREAM_SERVICE_NETWORK_ADDR}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh

source /package/shell_utils/init_utils.sh

${UTILS}/canonize_internal_api.py ${INNER_API_SCHEMA_DIR} ${MAIN_SERVICE_NAME}/${UPSTREAM_SERVICE}
#${UTILS}/build_common_api_services.py ${INNER_API_SCHEMA_DIR} -os ${WORK_DIR}/aux_services -oe ${WORK_DIR}
#${UTILS}/build_api_pseudo_fs.py ${INNER_API_SCHEMA_DIR} ${SHARED_API_DIR}

#${OPT_DIR}/api_management.py "${INNER_API_SCHEMA_DIR}" ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} &
#API_MANAGEMENT_PID=$!

#declare -A SERVICE_WATCH_PIDS
#termination_handler(){
#    gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}
#    exit 0
#}
#trap "termination_handler" SIGHUP SIGQUIT SIGABRT SIGKILL SIGALRM SIGTERM


#echo "run mock container API servers:"
#for s in ${WORK_DIR}/aux_services/*_server.sh; do
#    ${s} ${UTILS} &
#    SERVICE_WATCH_PIDS[${s}]=$!
#    echo "${s} has been started"
#done

echo "Run tests:"
RET=0
echo "EXCLUDE test_0_pseudo_fs_api_conformance.py"
rm -f ${WORK_DIR}/test_0_pseudo_fs_api_conformance.py
echo "EXCLUDE test_1_inner_api_functionality.py"
rm -f ${WORK_DIR}/test_1_inner_api_functionality.py
for s in ${WORK_DIR}/test_*.py; do
    #pytest -s ${s} -k 'test_unrechable_services'
    pytest -s ${s}
    VAL=$?
    if [ $VAL != 0 ]
    then
        RET=$VAL
    fi
done

rm -rf ${SHARED_API_DIR}/*
if [ $EXIT_ONCE_DONE == true ]; then exit $RET; fi

echo "wait for termination"
sleep infinity &
wait $!
exit $RET
