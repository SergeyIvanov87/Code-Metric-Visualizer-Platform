#!/usr/bin/bash

. /package/setenv.sh
echo "file with patch ${1}"
cd ${REPO_PATH}
cp ${SHARED_DIR}/${1} ./
patch -p1 < ${1} 

