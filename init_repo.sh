#!/usr/bin/bash

WORK_DIR=${1}
echo "REPO_PATH: ${WORK_DIR}"
git clone ${3} ${WORK_DIR}/my_repo

${WORK_DIR}/listen_fs.sh ${2}


