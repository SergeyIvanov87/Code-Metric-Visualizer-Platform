#!/usr/bin/bash

WORK_DIR=${1}
REPO_PATH=${2}
SHARED_DIR=${2}
SHARED_API_DIR=${2}/wingman.org

echo -e "#!/usr/bin/bash\n\nexport WORK_DIR=${WORK_DIR} \nexport SHARED_DIR=${SHARED_DIR} \nexport SHARED_API_DIR=${SHARED_API_DIR} \nexport REPO_PATH=${REPO_PATH}" > ${WORK_DIR}/setenv.sh

# allow wingman to access reposiroty
git config --global --add safe.directory ${REPO_PATH}

# create API directory and initialize API nodes
mkdir -p ${SHARED_API_DIR}
${WORK_DIR}/build_local_api.py "run" ${WORK_DIR}/API.replicated.fs ${SHARED_DIR}

# create pivot metrics
${WORK_DIR}/build_pmccabe_xml.sh "${SHARED_API_DIR}/init.xml"
${WORK_DIR}/build_pmccabe_flamegraph.sh "${SHARED_API_DIR}/init.xml" "${SHARED_API_DIR}/init.svg"

# run listener for events
for s in ${WORK_DIR}/services/*.sh; do
    ${s} ${WORK_DIR} ${SHARED_DIR} &
done

sleep infinity
