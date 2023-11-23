#!/usr/bin/bash

. /package/setenv.sh

XML_NAME=${1}
FLG_NAME=${2}
cat ${XML_NAME} | ${WORK_DIR}/pmccabe_visualizer/collapse.py -attr mmcc | ${WORK_DIR}/FlameGraph/flamegraph.pl > ${FLG_NAME}_mmcc.svg
cat ${XML_NAME} | ${WORK_DIR}/pmccabe_visualizer/collapse.py -attr tmcc | ${WORK_DIR}/FlameGraph/flamegraph.pl > ${FLG_NAME}_tmcc.svg
cat ${XML_NAME} | ${WORK_DIR}/pmccabe_visualizer/collapse.py -attr sif | ${WORK_DIR}/FlameGraph/flamegraph.pl > ${FLG_NAME}_sif.svg
cat ${XML_NAME} | ${WORK_DIR}/pmccabe_visualizer/collapse.py -attr lif | ${WORK_DIR}/FlameGraph/flamegraph.pl > ${FLG_NAME}_lif.svg
cat ${XML_NAME} | ${WORK_DIR}/pmccabe_visualizer/collapse.py -attr mmcc,tmcc,sif,lif | ${WORK_DIR}/FlameGraph/flamegraph.pl > ${FLG_NAME}_all.svg
