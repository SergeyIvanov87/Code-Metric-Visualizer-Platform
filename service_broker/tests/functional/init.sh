#!/bin/bash

export WORK_DIR=${1}
export SHARED_API_DIR=${2}
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

export PYTHONPATH="${WORK_DIR}:${WORK_DIR}/utils:${WORK_DIR}/utils/modules"
UTILS="${WORK_DIR}/utils"
export MODULES="${WORK_DIR}/utils/modules"

echo "Generate Mock API"
mv ${WORK_DIR}/API/service_broker_queries_order_list.json service_broker_queries_order_list.json
${UTILS}/build_api_executors.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}
${UTILS}/build_api_services.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}/services

rm -rf ${SHARED_API_DIR}/*
mkdir -p ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}
${UTILS}/build_api_pseudo_fs.py ${WORK_DIR}/API ${SHARED_API_DIR}

echo "run Mock API servers:"
if [ -d /tmp/test ]; then rm -rf /tmp/test; fi
mkdir -p /tmp/test
for s in ${WORK_DIR}/services/*_server.sh; do
    ${s} ${UTILS} &
    echo "${s} has been started"
done

echo "Run tests:"
echo "EXCLUDE test_0_pseudo_fs_api_conformance.py"
rm -f ${WORK_DIR}/test_0_pseudo_fs_api_conformance.py
for s in ${WORK_DIR}/test_*.py; do
    pytest -s ${s}
done


if [ $EXIT_ONCE_DONE == true ]; then exit $RET; fi

echo "wait for termination"
sleep infinity &
wait $!
exit $RET
