#!/bin/bash

export WORK_DIR=${1}
export SHARED_API_DIR=${2}
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

export PYTHONPATH="${WORK_DIR}:${WORK_DIR}/utils:${WORK_DIR}/utils/modules"
UTILS="${WORK_DIR}/utils"
export MODULES="${WORK_DIR}/utils/modules"

${UTILS}/canonize_internal_api.py ${WORK_DIR}/API/deps ${MAIN_SERVICE_NAME}/service_broker
mkdir -p /API
cp -r ${WORK_DIR}/API/deps /API/deps

echo "Generate Mock API"
mv ${WORK_DIR}/API/service_broker_queries_order_list.json service_broker_queries_order_list.json
mkdir -p ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}
for deps_service in ${WORK_DIR}/API/deps/*; do
    echo "Mock API from ${deps_service}"
    if [ -d ${deps_service} ];
    then
        echo "Mocking..."
        ${UTILS}/build_api_executors.py ${deps_service} ${WORK_DIR} -o ${WORK_DIR}
        ${UTILS}/build_api_services.py ${deps_service} ${WORK_DIR} -o ${WORK_DIR}/services
        ${UTILS}/build_api_pseudo_fs.py ${deps_service} ${SHARED_API_DIR}
    fi
done

echo "run Mock API servers:"
if [ -d /tmp/test ]; then rm -rf /tmp/test; fi
mkdir -p /tmp/test
for s in ${WORK_DIR}/services/*_server.sh; do
    ${s} ${UTILS} &
    echo "${s} has been started"
done

echo "Run tests:"
RET=0
echo "EXCLUDE test_0_pseudo_fs_api_conformance.py"
rm -f ${WORK_DIR}/test_0_pseudo_fs_api_conformance.py
for s in ${WORK_DIR}/test_*.py; do
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
