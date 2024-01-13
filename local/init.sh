#!/usr/bin/bash

WORK_DIR=${1}
INITIAL_PROJECT_LOCATION=${2}
SHARED_API_DIR=${2}/api.pmccabe_collector.restapi.org
MAIN_IMAGE_ENV_SHARED_LOCATION=${3}

echo -e "#!/usr/bin/bash\n\nexport WORK_DIR=${WORK_DIR} \nexport MAIN_IMAGE_ENV_SHARED_LOCATION=${MAIN_IMAGE_ENV_SHARED_LOCATION} \nexport SHARED_DIR=${SHARED_DIR} \nexport SHARED_API_DIR=${SHARED_API_DIR} \nexport INITIAL_PROJECT_LOCATION=${INITIAL_PROJECT_LOCATION} \nexport RRD_ROOT=${SHARED_API_DIR}" > ${MAIN_IMAGE_ENV_SHARED_LOCATION}/setenv.sh

# allow pmccabe_collector to access reposiroty
git config --global --add safe.directory ${INITIAL_PROJECT_LOCATION}

# create API directory and initialize API nodes
mkdir -p ${SHARED_API_DIR}
${MAIN_IMAGE_ENV_SHARED_LOCATION}/build_api_executors.py ${WORK_DIR}/API.replicated.fs ${MAIN_IMAGE_ENV_SHARED_LOCATION} -o ${WORK_DIR}
${MAIN_IMAGE_ENV_SHARED_LOCATION}/build_api_services.py ${WORK_DIR}/API.replicated.fs
${MAIN_IMAGE_ENV_SHARED_LOCATION}/build_api_pseudo_fs.py ${WORK_DIR}/API.replicated.fs ${INITIAL_PROJECT_LOCATION}

# TODO think about necessity in creating any pivot metrics
# There are few disadvantages about it:
# 1) for a large project it will introduce latency in container starting, because
# a lot of files requires more time to build statistic
# 2) It's not possible to pass an universal argument to configure source files lists
# for colelcting statistics and to specify any other precision parameters
# 3) taking into account the previous points the collected statistics might not apt
# for durther holistic analysis
#
# Conclusion: do not attempt to call any API commands to build statistic here in init.sh

#${WORK_DIR}/build_pmccabe_xml.sh ${MAIN_IMAGE_ENV_SHARED_LOCATION} "${SHARED_API_DIR}/init.xml"
#${WORK_DIR}/build_pmccabe_flamegraph.sh ${MAIN_IMAGE_ENV_SHARED_LOCATION} "${SHARED_API_DIR}/init.xml" "${SHARED_API_DIR}/init"

echo "run API listeners:"
for s in ${WORK_DIR}/services/*.sh; do
    ${s} ${MAIN_IMAGE_ENV_SHARED_LOCATION} &
    echo "${s} has been started"
done

sleep infinity
