#!/usr/bin/bash

WORK_DIR=${1}
INITIAL_PROJECT_LOCATION=${2}
SHARED_API_DIR=${2}/api.pmccabe_collector.restapi.org
MAIN_IMAGE_ENV_SHARED_LOCATION=${3}

# create API directory and initialize API nodes
mkdir -p ${SHARED_API_DIR}
${MAIN_IMAGE_ENV_SHARED_LOCATION}/build_api_services.py ${WORK_DIR}/API.replicated.fs
${MAIN_IMAGE_ENV_SHARED_LOCATION}/build_api_pseudo_fs.py ${WORK_DIR}/API.replicated.fs ${INITIAL_PROJECT_LOCATION}

echo "build RRD analytics"
BUILD_RRD_ARGS=`cd ${MAIN_IMAGE_ENV_SHARED_LOCATION} && python -c 'from read_api_fs_args import read_args; print(" ".join(read_args("'${SHARED_API_DIR}'/analytic/")))'`
echo ${BUILD_RRD_ARGS}
cat ${SHARED_API_DIR}/main/statistic/GET/exec
cat ${SHARED_API_DIR}/main/statistic/GET/result.xml | ${WORK_DIR}/build_rrd.py "`${WORK_DIR}/rrd_exec.sh ${MAIN_IMAGE_ENV_SHARED_LOCATION} ${SHARED_API_DIR}/analytic/rrd`" ${SHARED_API_DIR} -method init

echo "run API listeners:"
for s in ${WORK_DIR}/services/*.sh; do
    ${s} ${MAIN_IMAGE_ENV_SHARED_LOCATION} &
    echo "${s} has been started"
done

sleep infinity
