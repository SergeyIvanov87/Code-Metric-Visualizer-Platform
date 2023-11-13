#!/usr/bin/bash

WORK_DIR=${1}
REPO_PATH=${WORK_DIR}/my_repo
git clone ${3} ${REPO_PATH}

echo -e "#!/usr/bin/bash\n\nexport WORK_DIR=${WORK_DIR} \nexport SHARED_DIR=${2} \nexport REPO_PATH=${REPO_PATH}" > ${WORK_DIR}/setenv.sh

${WORK_DIR}/build_pmccabe_xml.sh head.xml
${WORK_DIR}/build_pmccabe_flamegraph.sh head.xml head.svg

${WORK_DIR}/listen_fs.sh ${2}

