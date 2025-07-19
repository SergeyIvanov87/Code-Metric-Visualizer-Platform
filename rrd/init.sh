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
README_FILE_PATH=${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc_analytic/README-API-ANALYTIC.md

# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport OPT_DIR=${OPT_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport RRD_DATA_STORAGE_DIR=${RRD_DATA_STORAGE_DIR}\nexport MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME}\nexport INNER_API_SCHEMA_DIR=${INNER_API_SCHEMA_DIR}\nexport DEPEND_ON_SERVICES_API_SCHEMA_DIR=${DEPEND_ON_SERVICES_API_SCHEMA_DIR}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh

source ${OPT_DIR}/shell_utils/color_codes.sh
if [ -z ${MICROSERVICE_NAME} ]; then
    echo -e "{BRed}ERROR: Please specify env/arg MICROSERVICE_NAME. Abort${Color_Off}"
    exit 255
fi
echo -e "${BGreen}Initializing: ${MICROSERVICE_NAME}...${Color_Off}"

# I use standalone python-based process here to listen to SIGNAL and make PIPEs clearance.
# For any reason, if I just esecute new python process in a trap handler then it will hangs for a long time until executed.
# The default timeour for graceful termination in docker compose exceeds this interval and the container would be killed ungracefully,
# which means no guarantee in PIPEs clearance and hang out processes unblocking
#
# So, to speed up this termination time until being ungracefully killed,
# I just launch this signal listener in background and then resend any signal being catched in the `trap`-handler
# It works as expected
source ${OPT_DIR}/shell_utils/init_utils.sh
API_MANAGEMENT_PID=0
declare -A SERVICE_WATCH_PIDS
termination_handler(){
    echo "gracefull, remove ${README_FILE_PATH}"
    rm -f ${README_FILE_PATH}
    gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}
    exit 0
}
trap "termination_handler" SIGHUP SIGQUIT SIGABRT SIGKILL SIGALRM SIGTERM

# create API directory and initialize API nodes
# TODO maybe should rely on build_seudo_fs.py?? as it create an entire  chain of directories
mkdir -p -m 777 ${SHARED_API_DIR}
TMPDIR=$(mktemp -d --tmpdir=${SHARED_API_DIR})
if [ $? -ne 0 ]; then echo "Cannot create ${SHARED_API_DIR}. Please check access rights to the VOLUME '/api' and grant the container all of them"; exit -1; fi
rm -rf $TMPDIR

mkdir -p -m 777 ${RRD_DATA_STORAGE_DIR}
if [ $? -ne 0 ]; then echo "Cannot create ${RRD_DATA_STORAGE_DIR}. Please check access rights to the VOLUME '/rrd_data' and grant the container all of them"; exit -1; fi


# Launch internal & command API services
launch_command_api_services SERVICE_WATCH_PIDS ${DEPEND_ON_SERVICES_API_SCHEMA_DIR} ${WORK_DIR} ${SHARED_API_DIR} "${MAIN_SERVICE_NAME}/${MICROSERVICE_NAME}"
launch_inner_api_services SERVICE_WATCH_PIDS ${INNER_API_SCHEMA_DIR} ${WORK_DIR} ${SHARED_API_DIR} ${README_FILE_PATH}
${OPT_DIR}/api_management.py "${INNER_API_SCHEMA_DIR}|${DEPEND_ON_SERVICES_API_SCHEMA_DIR}" ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} &
API_MANAGEMENT_PID=$!

echo -e "${Blue}Skip checking API dependencies${Color_Off}: ${BBlack}${SKIP_API_DEPS_CHECK}${Color_Off}"
if [ ! -z ${SKIP_API_DEPS_CHECK} ] && [ ${SKIP_API_DEPS_CHECK} == false ]; then
    wait_for_unavailable_services ${SHARED_API_DIR} "${MAIN_SERVICE_NAME}/${MICROSERVICE_NAME}" ANY_SERVICE_UNAVAILABLE_COUNT ${TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC}
    if [ ! -z ${ANY_SERVICE_UNAVAILABLE_COUNT} ]; then
        echo -e "${BRed}ERROR: As required APIs are missing, the service considered as inoperable. Abort${Color_Off}"
        gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}
        exit 255
    fi
fi

echo -e "${BGreen}The service is ready${Color_Off}"
sleep infinity &
wait $!
