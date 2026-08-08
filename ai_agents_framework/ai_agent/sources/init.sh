#!/bin/bash

export WORK_DIR=${1}
export INITIAL_PROJECT_LOCATION=${2}
export OPT_DIR=${3}
export SHARED_API_DIR=${4}
export PYTHONPATH="${3}:${3}/modules"

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

export VECTOR_DB_HOST=${VECTORDB_HOST}
export VECTOR_DB_PORT=${VECTORDB_PORT}

# generate assets in a tmp directory
export WORK_DIR_TMP=${WORK_DIR}/generated
mkdir -p ${WORK_DIR_TMP}

export INNER_API_SCHEMA_DIR=${WORK_DIR_TMP}/API

README_FILE_PATH=${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/ai_agent/README-API-STATISTIC.md

# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport WORK_DIR_TMP=${WORK_DIR_TMP}\nexport INITIAL_PROJECT_LOCATION=${INITIAL_PROJECT_LOCATION}\nexport OPT_DIR=${OPT_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME}\nexport INNER_API_SCHEMA_DIR=${INNER_API_SCHEMA_DIR}\nexport PYTHONPATH=${PYTHONPATH}\nexport VECTOR_DB_HOST=${VECTOR_DB_HOST}\nexport VECTOR_DB_PORT=${VECTOR_DB_PORT}" > ${WORK_DIR_TMP}/env.sh

cp -r /API ${WORK_DIR_TMP}
source ${OPT_DIR}/shell_utils/init_utils.sh

echo "Premature cleanup..."
rm -f ${README_FILE_PATH}
doas -u root env PYTHONPATH=${PYTHONPATH} SHARED_API_DIR=${SHARED_API_DIR} MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME} ${OPT_DIR}/api_management.py "${INNER_API_SCHEMA_DIR}" ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} &
doas -u root kill -15 $!


# I use standalone python-based process here to listen to SIGNAL and make PIPEs clearance.
# For any reason, if I just esecute new python process in a trap handler then it will hangs for a long time until executed.
# The default timeour for graceful termination in docker compose exceeds this interval and the container would be killed ungracefully,
# which means no guarantee in PIPEs clearance and hang out processes unblocking
#
# So, to speed up this termination time until being ungracefully killed,
# I just launch this signal listener in background and then resend any signal being catched in the `trap`-handler
# It works as expected
${OPT_DIR}/api_management.py ${INNER_API_SCHEMA_DIR} ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} &
API_MANAGEMENT_PID=$!

declare -A SERVICE_WATCH_PIDS
termination_handler(){
    #trap - SIGTERM
    rm -f ${README_FILE_PATH}
    gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}
    exit 0
}
trap "termination_handler" SIGHUP SIGQUIT SIGABRT SIGKILL SIGALRM SIGTERM EXIT

# TODO consider use launch_inner_api_services!
${OPT_DIR}/build_api_executors.py ${INNER_API_SCHEMA_DIR} ${WORK_DIR} -o ${WORK_DIR_TMP}
${OPT_DIR}/build_api_services.py ${INNER_API_SCHEMA_DIR} ${WORK_DIR_TMP} -o ${WORK_DIR_TMP}/services
doas -u root env PYTHONPATH=${PYTHONPATH} SHARED_API_DIR=${SHARED_API_DIR} MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME} ${OPT_DIR}/build_api_pseudo_fs.py ${INNER_API_SCHEMA_DIR} ${SHARED_API_DIR}
doas -u root chown -R $USER:$GROUPNAME ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/ai_agent

launch_fs_api_services SERVICE_WATCH_PIDS "${WORK_DIR_TMP}/services/"

echo -e "${BBlue}Populating README file...${Color_Off}"
${OPT_DIR}/make_api_readme.py ${INNER_API_SCHEMA_DIR}  | ( umask 0033; cat >> ${README_FILE_PATH} )

echo -e "${BGreen}The service is ready${Color_Off}"
sleep infinity &
wait $!
