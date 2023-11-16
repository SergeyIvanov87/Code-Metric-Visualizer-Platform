#!/usr/bin/bash

. /package/setenv.sh

XML_NAME=${1}
FLG_NAME=${2}
cat ${XML_NAME} | ${WORK_DIR}/pmccabe_visualizer/collapse.py mmcc,tmcc,sif,lif | ${WORK_DIR}/FlameGraph/flamegraph.pl > ${FLG_NAME}

