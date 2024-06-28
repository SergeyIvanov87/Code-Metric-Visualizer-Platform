#!/bin/sh

LOG_PREFIX="[WATCHDOG]: "
# file for storing a PID of a server instance
MY_REST_API_INSTANCE_PIDFILE=${1}
if [ -z ${MY_REST_API_INSTANCE_PIDFILE} ]; then
    MY_REST_API_INSTANCE_PIDFILE=/package/rest_api_server_pid
fi

MY_FLASK_RUN_HOST=${2}
if [ -z ${MY_FLASK_RUN_HOST} ]; then
    if [ -z ${FLASK_RUN_HOST} ]; then
        echo "${LOG_PREFIX}Neither MY_FLASK_RUN_HOST nor FLASK_RUN_HOST are set, it is impossible to launch watchdog without this env-variabled defined. Abort"
        exit 255
    fi
    MY_FLASK_RUN_HOST=${FLASK_RUN_HOST}
fi

MY_FLASK_RUN_PORT=${3}
if [ -z ${MY_FLASK_RUN_PORT} ]; then
    if [ -z ${FLASK_RUN_PORT} ]; then
        echo "${LOG_PREFIX}Neither MY_FLASK_RUN_PORT nor FLASK_RUN_PORT are set, it is impossible to launch watchdog without this env-variabled defined. Abort"
        exit 255
    fi
    MY_FLASK_RUN_PORT=${FLASK_RUN_PORT}
fi

let wait_for_file_API_counter=0
let wait_for_file_API_limit=4
let wait_for_api_exporting_directory_sec=15

let wait_for_file_API_initializing_by_its_owners_counter=0
let wait_for_file_API_initializing_by_its_owners_limit=5
let wait_for_api_initialization_by_its_owners_sec=1

let wait_for_server_starting_counter=0
let wait_for_server_starting_limit=5
let wait_for_server_starting_sec=1

while :
do
    rm -f ${MY_REST_API_INSTANCE_PIDFILE}
    # wait for API directory creation
    if [ ! -d "${SHARED_API_DIR}/${MAIN_SERVICE_NAME}" ]; then
        if [ ${wait_for_file_API_counter} == ${wait_for_file_API_limit} ]; then
            echo "${LOG_PREFIX}API exporting directory has not been served as expected. Abort"
            rm -f ${MY_REST_API_INSTANCE_PIDFILE}
            exit 255
        fi
        let wait_for_file_API_counter=$wait_for_file_API_counter+1
        echo "${LOG_PREFIX}API exporting directory: ${SHARED_API_DIR}/${MAIN_SERVICE_NAME} - doesn't exist. Another attempt: ${wait_for_file_API_counter}/${wait_for_file_API_limit} - will be made in ${wait_for_api_exporting_directory_sec} seconds."
        sleep ${wait_for_api_exporting_directory_sec} &
        wait $!
        continue
    fi

    # clear existing generated API schema files to facilitate clear-build environment
    rm -f ${WORK_DIR}/restored_API/*
    ${OPT_DIR}/restore_api_from_pseudo_fs.py ${SHARED_API_DIR} ${MAIN_SERVICE_NAME} ${WORK_DIR}/restored_API

    # wait for API files
    if [ `ls ${WORK_DIR}/restored_API/*.json | wc -l` == 0 ]; then
        if [ ${wait_for_file_API_counter} == ${wait_for_file_API_limit} ]; then
            echo "${LOG_PREFIX}API exporting directory contains no JSON data. Abort"
            rm -f ${MY_REST_API_INSTANCE_PIDFILE}
            exit 255
        fi
        let wait_for_file_API_counter=$wait_for_file_API_counter+1
        echo "${LOG_PREFIX}Nothing was gathered from the API directory: ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}. Please check your exporting API. Another attempt: ${wait_for_file_API_counter}/${wait_for_file_API_limit} - will be made in ${wait_for_api_exporting_directory_sec} seconds."
        sleep ${wait_for_api_exporting_directory_sec} &
        wait $!
        continue
    fi

    # wait for Markdown files
    if [ ! -f ${WORK_DIR}/restored_API/index.md ]; then
        if [ ${wait_for_file_API_initializing_by_its_owners_counter} == ${wait_for_file_API_initializing_by_its_owners_limit} ]; then
            echo "${LOG_PREFIX}Can't find API README from'${WORK_DIR}/restored_API/index.md' - probably filesystem API is inconsistent. REST_API server won't serve any request and will be stopped"
            rm -f ${MY_REST_API_INSTANCE_PIDFILE}
            exit 255
        fi
        let wait_for_file_API_initializing_by_its_owners_counter=$wait_for_file_API_initializing_by_its_owners_counter+1
        echo "${LOG_PREFIX}File ${WORK_DIR}/restored_API/index.md hasn't been recreated yet. Probably APIs were not initialized entirely. Another attempt: ${wait_for_file_API_initializing_by_its_owners_counter}/${wait_for_file_API_initializing_by_its_owners_limit} - will be made in ${wait_for_api_initialization_by_its_owners_sec} seconds."
        sleep ${wait_for_api_initialization_by_its_owners_sec} &
        wait $!
        continue
    fi

    echo "${LOG_PREFIX}Generate REST_API CGIs from imported API entry point"
    rm -f ${WORK_DIR}/rest_api_server/rest_api_server/cgi.py
    cp ${WORK_DIR}/rest_api_server/rest_api_server/cgi_template.py ${WORK_DIR}/rest_api_server/rest_api_server/cgi.py
    ${WORK_DIR}/build_api_cgi.py ${WORK_DIR}/restored_API ${SHARED_API_DIR} ${MAIN_SERVICE_NAME} >> ${WORK_DIR}/rest_api_server/rest_api_server/cgi.py
    cp ${WORK_DIR}/restored_API/index.md  ${WORK_DIR}/rest_api_server/rest_api_server/templates/
    cd ${WORK_DIR}/rest_api_server/

    echo "${LOG_PREFIX}Start REST_API server"
    pipx install -e .
    python -m flask run &
    SERVER_INSTANCE_PID=$!
    SERVER_INSTANCE_RET=$?
    if [ ${SERVER_INSTANCE_RET} != 0 ]; then
        echo "${LOG_PREFIX}Cannot start the server instance, error: ${SERVER_INSTANCE_RET}"
        exit 255
    fi

    let wait_for_file_API_counter=0
    let wait_for_file_API_initializing_by_its_owners_counter=0
    wait_for_server_starting_counter=0
    SERVICE=http://${MY_FLASK_RUN_HOST}:${MY_FLASK_RUN_PORT}
    echo "${LOG_PREFIX}Waiting for a new server instance being initialed on: ${SERVICE}..."
    while :
    do
        curl -I -s -o /dev/null ${SERVICE}
        if [ $? -eq 0 ];
        then
            break
        fi

        if [ ${wait_for_server_starting_counter} == ${wait_for_server_starting_limit} ]; then
            echo "${LOG_PREFIX}Service ${SERVICE} has not been initialized. Abort"
            exit 255
        fi
        let wait_for_server_starting_counter=$wait_for_server_starting_counter+1
        echo "${LOG_PREFIX}Service ${SERVICE} is offline. Another attempt: ${wait_for_server_starting_counter}/${wait_for_server_starting_limit} - will be made in ${wait_for_server_starting_sec} seconds."
        sleep ${wait_for_server_starting_sec} &
        wait $!
        continue
    done

    echo ${SERVER_INSTANCE_PID} > ${MY_REST_API_INSTANCE_PIDFILE}
    echo "${LOG_PREFIX}The new server instance has been started, PID: ${SERVER_INSTANCE_PID}"
    wait ${SERVER_INSTANCE_PID}
done
