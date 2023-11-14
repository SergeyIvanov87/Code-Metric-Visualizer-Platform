#!/usr/bin/bash

WORK_DIR=${1}
REPO_PATH=${2}
SHARED_DIR=${2}/pmccabe

echo -e "#!/usr/bin/bash\n\nexport WORK_DIR=${WORK_DIR} \nexport SHARED_DIR=${SHARED_DIR} \nexport REPO_PATH=${REPO_PATH}" > ${WORK_DIR}/setenv.sh

#allow wingman to access reposiroty
git config --global --add safe.directory ${REPO_PATH}

mkdir -p ${SHARED_DIR}

# create pivot metrics
${WORK_DIR}/build_pmccabe_xml.sh "${SHARED_DIR}/init.xml"
${WORK_DIR}/build_pmccabe_flamegraph.sh "${SHARED_DIR}/init.xml" "${SHARED_DIR}/init.svg"

# run listener for events
${WORK_DIR}/listen.sh ${SHARED_DIR}
