#!/bin/bash

export WORK_DIR=${1}
export DISPATCHER_SETTINGS_DIR=${2}
export OPT_DIR=${3}
export SHARED_API_DIR=${4}
export PYTHONPATH="${3}:${3}/modules"

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

# generate assets in a tmp directory
export WORK_DIR_TMP=${WORK_DIR}/generated
mkdir -p ${WORK_DIR_TMP}

export INNER_API_SCHEMA_DIR=${WORK_DIR_TMP}/API

README_FILE_PATH=${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/ai_agent_rag_dispatcher/README-API-DOCS-DISPATCHER.md

# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport WORK_DIR_TMP=${WORK_DIR_TMP}\nexport DISPATCHER_SETTINGS_DIR=${DISPATCHER_SETTINGS_DIR}\nexport OPT_DIR=${OPT_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME}\nexport INNER_API_SCHEMA_DIR=${INNER_API_SCHEMA_DIR}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh

cp -r /API ${WORK_DIR_TMP}
source ${OPT_DIR}/shell_utils/init_utils.sh

echo "set premature cleanup handlers..."
rm -f ${README_FILE_PATH}
doas -u root env PYTHONPATH=${PYTHONPATH} SHARED_API_DIR=${SHARED_API_DIR} MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME} ${OPT_DIR}/api_management.py "${INNER_API_SCHEMA_DIR}" ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} &
api_management_pid=$!
while true
do
    doas -u root kill -s 0 ${api_management_pid} > /dev/null 2>&1
    RESULT=$?
    if [ $RESULT != 0 ]; then
        sleep 1
        continue
    fi
    break
done
echo "make premature cleanup handlers..."
doas -u root kill -s SIGTERM ${api_management_pid}

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
doas -u root chown -R $USER:$GROUPNAME ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/ai_agent_rag_dispatcher

launch_fs_api_services SERVICE_WATCH_PIDS "${WORK_DIR_TMP}/services/"

# sync data
${WORK_DIR}/sync.py


echo -e "${BBlue}Populating README file...${Color_Off}"
${OPT_DIR}/make_api_readme.py ${INNER_API_SCHEMA_DIR}  | ( umask 0033; cat >> ${README_FILE_PATH} )

echo -e "${BGreen}The service is ready${Color_Off}"
sleep infinity &
wait $!
