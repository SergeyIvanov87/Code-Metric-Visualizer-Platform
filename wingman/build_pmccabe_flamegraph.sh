#!/usr/bin/bash

. /package/setenv.sh

XML_NAME=${1}
FLG_NAME=${2}
cat ${SHARED_DIR}/${XML_NAME} | ${WORK_DIR}/pmccabe_visualizer/collapse.py mmcc,tmcc,sif,lif | ${WORK_DIR}/FlameGraph/flamegraph.pl > ${SHARED_DIR}/${FLG_NAME}

