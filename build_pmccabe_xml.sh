#!/usr/bin/bash

. /package/setenv.sh

XML_NAME=${1}
find ${REPO_PATH} -regex ".*\.\(hpp\|cpp\|c\|h\)" | grep -v "buil" | grep -v "3pp" | grep -v "thirdpart" | ${WORK_DIR}/pmccabe_visualizer/pmccabe_build.py > ${SHARED_DIR}/${1}

