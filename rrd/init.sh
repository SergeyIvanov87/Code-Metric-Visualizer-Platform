#!/bin/bash

export WORK_DIR=${1}
export OPT_DIR=${2}
export PYTHONPATH="${2}:${2}/modules"
export SHARED_API_DIR=${3}
export RRD_DATA_STORAGE_DIR=${4}/api.pmccabe_collector.restapi.org

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org
export DEPEND_ON_SERVICES_API_SCHEMA_DIR=${WORK_DIR}/API/deps
export INNER_API_SCHEMA_DIR=${WORK_DIR}/API

##### why cc instead of rrd?
README_FILE_PATH=${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/README-API-ANALYTIC.md

# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport OPT_DIR=${OPT_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport RRD_DATA_STORAGE_DIR=${RRD_DATA_STORAGE_DIR}\nexport MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME}\nexport INNER_API_SCHEMA_DIR=${INNER_API_SCHEMA_DIR}\nexport DEPEND_ON_SERVICES_API_SCHEMA_DIR=${DEPEND_ON_SERVICES_API_SCHEMA_DIR}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh

source ${OPT_DIR}/shell_utils/init_utils.sh

# I use standalone python-based process here to listen to SIGNAL and make PIPEs clearance.
# For any reason, if I just esecute new python process in a trap handler then it will hangs for a long time until executed.
# The default timeour for graceful termination in docker compose exceeds this interval and the container would be killed ungracefully,
# which means no guarantee in PIPEs clearance and hang out processes unblocking
#
# So, to speed up this termination time until being ungracefully killed,
# I just launch this signal listener in background and then resend any signal being catched in the `trap`-handler
# It works as expected
${OPT_DIR}/canonize_internal_api.py ${DEPEND_ON_SERVICES_API_SCHEMA_DIR} ${MAIN_SERVICE_NAME}/rrd
${OPT_DIR}/api_management.py "${INNER_API_SCHEMA_DIR}|${DEPEND_ON_SERVICES_API_SCHEMA_DIR}" ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} &
API_MANAGEMENT_PID=$!

declare -A SERVICE_WATCH_PIDS
termination_handler(){
    rm -f ${README_FILE_PATH}
    gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}
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


# Launch internal API services
${OPT_DIR}/build_common_api_services.py ${DEPEND_ON_SERVICES_API_SCHEMA_DIR} -os ${WORK_DIR}/aux_services -oe ${WORK_DIR}
${OPT_DIR}/build_api_pseudo_fs.py ${DEPEND_ON_SERVICES_API_SCHEMA_DIR} ${SHARED_API_DIR}

launch_fs_api_services SERVICE_WATCH_PIDS "${WORK_DIR}/aux_services"

${OPT_DIR}/build_api_executors.py ${INNER_API_SCHEMA_DIR} ${WORK_DIR} -o ${WORK_DIR}
${OPT_DIR}/build_api_services.py ${INNER_API_SCHEMA_DIR} ${WORK_DIR} -o ${WORK_DIR}/services
${OPT_DIR}/build_api_pseudo_fs.py ${INNER_API_SCHEMA_DIR} ${SHARED_API_DIR}
${OPT_DIR}/make_api_readme.py ${INNER_API_SCHEMA_DIR} > ${README_FILE_PATH}

launch_fs_api_services SERVICE_WATCH_PIDS "${WORK_DIR}/services"

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


echo -e "${Blue}Skip checking API dependencies${Color_Off}: ${BBlack}${SKIP_API_DEPS_CHECK}${Color_Off}"
if [ ! -z ${SKIP_API_DEPS_CHECK} ] && [ ${SKIP_API_DEPS_CHECK} == false ]; then
    wait_for_unavailable_services ${SHARED_API_DIR} "${MAIN_SERVICE_NAME}/rrd" ANY_SERVICE_UNAVAILABLE_COUNT
    if [ ! -z ${ANY_SERVICE_UNAVAILABLE_COUNT} ]; then
        echo -e "${BRed}ERROR: As required APIs are missing, the service considered as inoperable. Abort${Color_Off}"
        gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}
        exit 255
    fi
fi

echo -e "${BGreen}The service is ready${Color_Off}"
sleep infinity &
wait $!
