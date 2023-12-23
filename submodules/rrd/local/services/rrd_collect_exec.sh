#!/usr/bin/bash

API_NODE=${1}
. $2/setenv.sh
RESULT_FILE=${3}_result
CMD_ARGS=""
for entry in "${API_NODE}"/*.*
do
    file_basename=${entry##*/}
    param_name=${file_basename#*.}
    readarray -t arr < ${entry}
    special_kind_param_name=${param_name%.*}
    if [[ ${special_kind_param_name} != 'NO_NAME_PARAM' ]];
    then
        brr+=(${param_name})
    fi
    for a in ${arr[@]}
    do
        if [[ ${a} == \"* ]];
        then
            brr+=("${a}")
        else
            brr+=(${a})
        fi
    done
done
cat ${SHARED_API_DIR}/init.xml | ${WORK_DIR}/build_rrd.py "`${WORK_DIR}/rrd_exec.sh ${SHARED_API_DIR}/project/{uuid}/analytic/rrd ${WORK_DIR} rd`" ${SHARED_API_DIR} ${brr[@]}
