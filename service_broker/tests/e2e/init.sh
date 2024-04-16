#!/bin/bash

export WORK_DIR=${1}
export SHARED_API_DIR=${2}
export UTILS="/main_image_env"
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

echo "Generate Mock API"
mv ${WORK_DIR}/API/service_broker_queries_order_list.json service_broker_queries_order_list.json
${UTILS}/build_api_executors.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}
${UTILS}/build_api_services.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}/services
mkdir -p ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}
${UTILS}/build_api_pseudo_fs.py ${WORK_DIR}/API ${SHARED_API_DIR}

echo "run Mock API servers:"
if [ -d /tmp/test ]; then rm -rf /tmp/test; fi
mkdir -p /tmp/test
for s in ${WORK_DIR}/services/*_server.sh; do
    ${s} ${MAIN_IMAGE_ENV_SHARED_LOCATION} &
    echo "${s} has been started"
done

echo "Run tests:"
for s in ${WORK_DIR}/test_*.py; do
    pytest ${s}
done
