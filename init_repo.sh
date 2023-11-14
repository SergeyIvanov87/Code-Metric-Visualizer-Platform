#!/usr/bin/bash

WORK_DIR=${1}
REPO_PATH=${WORK_DIR}/my_repo
git clone ${3} ${REPO_PATH}

if [ -z "${4}" ]; then
    REPO_BRANCH="main"
else
    REPO_BRANCH=${4}
fi

echo -e "#!/usr/bin/bash\n\nexport WORK_DIR=${WORK_DIR} \nexport SHARED_DIR=${2} \nexport REPO_PATH=${REPO_PATH} \nREPO_BRANCH=${REPO_BRANCH}" > ${WORK_DIR}/setenv.sh

${WORK_DIR}/build_pmccabe_xml.sh "${REPO_BRANCH}.xml"
${WORK_DIR}/build_pmccabe_flamegraph.sh "${REPO_BRANCH}.xml" "${REPO_BRANCH}.svg"

${WORK_DIR}/listen_fs.sh ${2}

