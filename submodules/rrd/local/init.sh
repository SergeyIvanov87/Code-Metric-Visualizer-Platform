#!/usr/bin/bash

WORK_DIR=${1}
REPO_PATH=${2}
SHARED_DIR=${2}
SHARED_API_DIR=${2}/api.pmccabe_collector.restapi.org
COMMON_UTIL_PATH=${WORK_DIR}

echo -e "#!/usr/bin/bash\n\nexport WORK_DIR=${WORK_DIR} \nexport SHARED_DIR=${SHARED_DIR} \nexport SHARED_API_DIR=${SHARED_API_DIR} \nexport REPO_PATH=${REPO_PATH} \nexport RRD_ROOT=${SHARED_API_DIR}" > ${WORK_DIR}/setenv.sh

# create API directory and initialize API nodes
mkdir -p ${SHARED_API_DIR}
${COMMON_UTIL_PATH}/build_api_pseudo_fs.py ${WORK_DIR}/API.replicated.fs ${SHARED_DIR}

echo "build RRD analytics"
BUILD_RRD_ARGS=`cd ${WORK_DIR} && python -c 'from read_api_fs_args import read_args; print(" ".join(read_args("'${SHARED_API_DIR}'/project/{uuid}/analytic/")))'`
echo ${BUILD_RRD_ARGS}
cat ${SHARED_API_DIR}/init.xml | ${WORK_DIR}/build_rrd.py "`${WORK_DIR}/rrd_exec.sh ${SHARED_API_DIR}/project/{uuid}/analytic/rrd ${WORK_DIR} anlt`" ${SHARED_API_DIR} -method init

echo "run API listeners:"
for s in ${WORK_DIR}/services/*.sh; do
    ${s} ${WORK_DIR} ${SHARED_API_DIR} &
    echo "${s} has been started"
done

sleep infinity
