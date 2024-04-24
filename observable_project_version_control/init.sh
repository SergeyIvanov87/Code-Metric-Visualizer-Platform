#!/bin/bash

export WORK_DIR=${1}
export INITIAL_PROJECT_LOCATION=${2}
export OPT_DIR=${3}
export PYTHONPATH="${3}:${3}/modules"
export SHARED_API_DIR=${4}

# allow pmccabe_collector to access reposiroty
git clone ${PROJECT_URL} -b ${PROJECT_BRANCH} ${INITIAL_PROJECT_LOCATION}

# create API directory and initialize API nodes
mkdir -p ${SHARED_API_DIR}
${OPT_DIR}/build_api_executors.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}
${OPT_DIR}/build_api_services.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}/services
${OPT_DIR}/build_api_pseudo_fs.py ${WORK_DIR}/API ${SHARED_API_DIR}
${OPT_DIR}/make_api_readme.py ${WORK_DIR}/API > ${SHARED_API_DIR}/api.pmccabe_collector.restapi.org/project/README-API-STATISTIC.md

echo "run API listeners:"
for s in ${WORK_DIR}/services/*.sh; do
    ${s} &
    echo "${s} has been started"
done

sleep infinity
