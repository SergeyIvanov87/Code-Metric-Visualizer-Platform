#!/bin/bash

export WORK_DIR=${1}
export SHARED_API_DIR=${2}

export UTILS="/main_image_env"

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

mv ${WORK_DIR}/data/portal.json portal.json
${UTILS}/build_api_executors.py ${WORK_DIR}/data ${WORK_DIR} -o ${WORK_DIR}
${UTILS}/build_api_services.py ${WORK_DIR}/data ${WORK_DIR} -o ${WORK_DIR}/services
mkdir -p ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}
${UTILS}/make_api_readme.py ${WORK_DIR}/data > ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/README-API-MOCK.md
${UTILS}/build_api_pseudo_fs.py ${WORK_DIR}/data ${SHARED_API_DIR}


echo "run Mock API servers:"
for s in ${WORK_DIR}/services/*_server.sh; do
    ${s} ${MAIN_IMAGE_ENV_SHARED_LOCATION} &
    echo "${s} has been started"
done

# TODO temporary solution sleep 30:
sleep 40

# clear existing generated API schema files to facilitate clear-build environment
rm -fr ${WORK_DIR}/restored_API
mkdir -p ${WORK_DIR}/restored_API
${UTILS}/restore_api_from_pseudo_fs.py ${SHARED_API_DIR} ${MAIN_SERVICE_NAME} ${WORK_DIR}/restored_API

echo "Run tests:"
mv portal.json ${WORK_DIR}/restored_API/portal.json
for s in ${WORK_DIR}/test_*.py; do
    pytest ${s}
done
