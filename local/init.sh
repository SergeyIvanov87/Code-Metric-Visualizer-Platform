#!/usr/bin/bash

WORK_DIR=${1}
INITIAL_PROJECT_LOCATION=${2}
SHARED_API_DIR=${2}/api.pmccabe_collector.restapi.org
MAIN_IMAGE_ENV_SHARED_LOCATION=${WORK_DIR}

echo -e "#!/usr/bin/bash\n\nexport WORK_DIR=${WORK_DIR} \nexport MAIN_IMAGE_ENV_SHARED_LOCATION=${MAIN_IMAGE_ENV_SHARED_LOCATION} \nexport SHARED_DIR=${SHARED_DIR} \nexport SHARED_API_DIR=${SHARED_API_DIR} \nexport INITIAL_PROJECT_LOCATION=${INITIAL_PROJECT_LOCATION} \nexport RRD_ROOT=${SHARED_API_DIR}" > ${MAIN_IMAGE_ENV_SHARED_LOCATION}/setenv.sh

# allow pmccabe_collector to access reposiroty
git config --global --add safe.directory ${INITIAL_PROJECT_LOCATION}

# create API directory and initialize API nodes
mkdir -p ${SHARED_API_DIR}
${MAIN_IMAGE_ENV_SHARED_LOCATION}/build_api_pseudo_fs.py ${WORK_DIR}/API.replicated.fs ${INITIAL_PROJECT_LOCATION}

echo "create pivot metrics"
${WORK_DIR}/build_pmccabe_xml.sh ${MAIN_IMAGE_ENV_SHARED_LOCATION} "${SHARED_API_DIR}/init.xml"
${WORK_DIR}/build_pmccabe_flamegraph.sh ${MAIN_IMAGE_ENV_SHARED_LOCATION} "${SHARED_API_DIR}/init.xml" "${SHARED_API_DIR}/init"

echo "build RRD analytics"
BUILD_RRD_ARGS=`cd ${WORK_DIR} && python -c 'from read_api_fs_args import read_args; print(" ".join(read_args("'${SHARED_API_DIR}'/analytic/")))'`
echo ${BUILD_RRD_ARGS}
cat ${SHARED_API_DIR}/init.xml | ${WORK_DIR}/build_rrd.py "`${WORK_DIR}/rrd_exec.sh ${MAIN_IMAGE_ENV_SHARED_LOCATION} ${SHARED_API_DIR}/analytic/rrd anlt`" ${SHARED_API_DIR} -method init

echo "run API listeners:"
for s in ${WORK_DIR}/services/*.sh; do
    ${s} ${WORK_DIR} &
    echo "${s} has been started"
done

sleep infinity
