#!/usr/bin/bash

API_NODE=${1}
. $2/setenv.sh
RESULT_FILE=${3}_result
echo "`${WORK_DIR}/rrd_select_exec.sh ${SHARED_API_DIR}/project/{uuid}/analytic/rrd/select ${WORK_DIR} se`" | xargs find ${RRD_ROOT} | ${WORK_DIR}/fetch_rrd.py ${SHARED_API_DIR}/project/{uuid}/analytic/rrd/select/view > ${RESULT_FILE}_csv_in_progress
mv ${RESULT_FILE}_csv_in_progress ${RESULT_FILE}.csv
