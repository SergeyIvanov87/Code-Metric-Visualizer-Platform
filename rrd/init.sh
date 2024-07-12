#!/bin/bash

export WORK_DIR=${1}
export OPT_DIR=${2}
export PYTHONPATH="${2}:${2}/modules"
export SHARED_API_DIR=${3}
export RRD_DATA_STORAGE_DIR=${4}/api.pmccabe_collector.restapi.org

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

README_FILE_PATH=${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/README-API-ANALYTIC.md

# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport OPT_DIR=${OPT_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport RRD_DATA_STORAGE_DIR=${RRD_DATA_STORAGE_DIR}\nexport MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh

# I use standalone python-based process here to listen to SIGNAL and make PIPEs clearance.
# For any reason, if I just esecute new python process in a trap handler then it will hangs for a long time until executed.
# The default timeour for graceful termination in docker compose exceeds this interval and the container would be killed ungracefully,
# which means no guarantee in PIPEs clearance and hang out processes unblocking
#
# So, to speed up this termination time until being ungracefully killed,
# I just launch this signal listener in background and then resend any signal being catched in the `trap`-handler
# It works as expected
${OPT_DIR}/api_management.py ${WORK_DIR}/API/ ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} &
API_MANAGEMENT_PID=$!

declare -A SERVICE_WATCH_PIDS
termination_handler(){
    trap - SIGTERM
    echo "`date +%H:%M:%S:%3N`    ***Shutdown servers***"
    ps -ef
    rm -f ${README_FILE_PATH}
    for server_script_path in "${!SERVICE_WATCH_PIDS[@]}"
    do
        echo "Kill ${server_script_path} by PID: {${SERVICE_WATCH_PIDS[$server_script_path]}}"
        pkill -KILL -e -P ${SERVICE_WATCH_PIDS[$server_script_path]}
        kill -9 ${SERVICE_WATCH_PIDS[$server_script_path]}
        ps -ef
    done
    echo "`date +%H:%M:%S:%3N`    ***Clear pipes****"
    kill -s SIGTERM ${API_MANAGEMENT_PID}
    while true
    do
        kill -s 0 ${API_MANAGEMENT_PID}
        RESULT=$?
        if [ $RESULT == 0 ]; then
            continue
        fi
        break
    done
    echo "`date +%H:%M:%S:%3N`    ***Done****"
    exit 0
}
trap "termination_handler" SIGHUP SIGQUIT SIGABRT SIGKILL SIGALRM SIGTERM

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
${OPT_DIR}/make_api_readme.py ${WORK_DIR}/API > ${README_FILE_PATH}

echo "run API listeners:"
for s in ${WORK_DIR}/services/*.sh; do
    /bin/bash ${s} &
    SERVICE_WATCH_PIDS[${s}]=$!
    echo "${s} has been started, PID ${SERVICE_WATCH_PIDS[${s}]}"
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
