#!/bin/bash

export WORK_DIR=${1}
export OPT_DIR=${2}
export PYTHONPATH="${2}:${2}/modules"
export SHARED_API_DIR=${3}
export RRD_DATA_STORAGE_DIR=${4}/api.pmccabe_collector.restapi.org

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

# create API directory and initialize API nodes
mkdir -p ${SHARED_API_DIR}
TMPDIR=$(mktemp -d --tmpdir=${SHARED_API_DIR})
if [ $? -ne 0 ]; then echo "Cannot create ${SHARED_API_DIR}. Please check access rights to the VOLUME '/api' and grant the container all of them"; exit -1; fi
rm -rf $TMPDIR

mkdir -p ${RRD_DATA_STORAGE_DIR}
if [ $? -ne 0 ]; then echo "Cannot create ${RRD_DATA_STORAGE_DIR}. Please check access rights to the VOLUME '/rrd_data' and grant the container all of them"; exit -1; fi

${OPT_DIR}/build_api_executors.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}
${OPT_DIR}/build_api_services.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}/services
${OPT_DIR}/build_api_pseudo_fs.py ${WORK_DIR}/API ${SHARED_API_DIR}
${OPT_DIR}/make_api_readme.py ${WORK_DIR}/API > ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/README-API-ANALYTIC.md

# TODO think about making commit an initial RRD transaction at container starting or ask for user decision
# There are few disadvantages about asking through STDIN:
# 1) starting container cannot be easily automized: you need to provide [Y/n] during startup procedure
# 2) it have to use STDIN/OUT
# 3) it requires for decision made depends on the container started first time or sequentially
#
# THe more favourable way is to not try to start colectinf analytics unconditionally or ask for user about it but rather
# abandon any attempt to make it and keep container start-up process clear from any cumbersome logic.
# So only services must be started up here!

#BUILD_RRD_ARGS=`cd ${OPT_DIR} && python -c 'import os; import sys; sys.path.append(os.environ["MAIN_IMAGE_ENV_SHARED_LOCATION_ENV"]); from api_fs_args import read_args; print(" ".join(read_args("'${SHARED_API_DIR}'/cc/analytic/")))'`
#BUILD_RRD_COUNTERS_ARGS=`cd ${OPT_DIR} && python -c 'import os; import sys; sys.path.append(os.environ["MAIN_IMAGE_ENV_SHARED_LOCATION_ENV"]); from api_fs_args import read_args; print(" ".join(read_args("'${SHARED_API_DIR}'/cc/analytic/rrd")))'`
#BUILD_RRD_FROM_SOURCES=`cd ${OPT_DIR} && python -c 'import os; import sys; sys.path.append(os.environ["MAIN_IMAGE_ENV_SHARED_LOCATION_ENV"]); from api_fs_args import read_args; print(" ".join(read_args("'${SHARED_API_DIR}'/cc/")))'`

#printf "INFO: Set up 'api.pmccabe_collector.restapi.org/cc/analytic' params before proceed.\n"
#printf "Default params would be used otherwise:\n"
#printf "\tSource files search engine: \t'find ${BUILD_RRD_FROM_SOURCES}'\n"
#printf "\tMetrics evaluation interval: \t${BUILD_RRD_ARGS}\n\n"
#yesno="Y"
#answers="yYnN"
#loop=1
#while [ $loop -ne 0 ]; do
#    read -n 1 -p "Commit RRD database filing? [Y/n]: " yesno
#    if [ "${yesno}" == "" ]; then
#       yesno="Y"
#    fi
#
#    for (( i=0; i<${#answers}; i++ )); do
#       if [ "${yesno}" == "${answers:$i:1}" ]
#       then
#            loop=0
#            break
#       fi
#    done
#    printf '\n'
#done

termination_handler(){
   echo "***Stopping"
   exit 0
}

echo "Setup signal handlers"
trap 'termination_handler' SIGTERM

echo "run API listeners:"
for s in ${WORK_DIR}/services/*.sh; do
    /bin/bash ${s} &
    echo "${s} has been started"
done

#TODO find better solution
#sleep 5
#if [ ${yesno} == "y" -o ${yesno} == "Y" ]; then
#    echo "Commiting RRD transaction..."

    # In order to be able to make pipeline of commands outputs need to read from PUT values pairs with '=' instead of ' '???
    #echo 0 > ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/analytic/PUT/exec
    #cat ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/analytic/PUT/result > ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/statistic/GET/exec
#    echo 0 > ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/statistic/GET/exec
#    cat ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/statistic/GET/result.xml | ${WORK_DIR}/build_rrd.py "`${WORK_DIR}/rrd_exec.sh ${OPT_DIR} ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/analytic/rrd`" ${SHARED_API_DIR} -method init
#    echo "Completed"
#fi

sleep infinity &
wait $!
