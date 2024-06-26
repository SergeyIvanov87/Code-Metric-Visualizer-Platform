#!/bin/bash

export WORK_DIR=${1}
export SHARED_API_DIR=${2}

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org
export PYTHONPATH="${WORK_DIR}:${WORK_DIR}/utils:${WORK_DIR}/utils/modules"
UTILS="${WORK_DIR}/utils"
export MODULES="${WORK_DIR}/utils/modules"

mv ${WORK_DIR}/data/portal.json portal.json
${UTILS}/build_api_executors.py ${WORK_DIR}/data ${WORK_DIR} -o ${WORK_DIR}
${UTILS}/build_api_services.py ${WORK_DIR}/data ${WORK_DIR} -o ${WORK_DIR}/services

rm -rf ${SHARED_API_DIR}/*
mkdir -p ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}
${UTILS}/build_api_pseudo_fs.py ${WORK_DIR}/data ${SHARED_API_DIR}
${UTILS}/make_api_readme.py ${WORK_DIR}/data > ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/README-API-MOCK.md

echo "run Mock API servers:"
for s in ${WORK_DIR}/services/*_server.sh; do
    ${s} &
    echo "${s} has been started"
done

echo "wait for termination"
sleep infinity &
wait $!
exit 0
