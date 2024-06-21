#!/bin/sh

export WORK_DIR=${1}
export OPT_DIR=${2}
export PYTHONPATH="${2}:${2}/modules"

export SHARED_API_DIR=${3}
MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

termination_handler(){
   echo "***Stopping"
   exit 0
}

echo "Setup signal handlers"
trap 'termination_handler' SIGTERM

echo "DEBUG CMD:"
    echo "cp ../rest_api_server/rest_api_server/cgi_template.py ../rest_api_server/rest_api_server/cgi.py && ../build_api_cgi.py ../restored_API /api api.pmccabe_collector.restapi.org >> ../rest_api_server/rest_api_server/cgi.py"
    echo "flask --app rest_api_server run --host 0.0.0.0"

let wait_for_file_API_counter=0
let wait_for_file_API_limit=4
let wait_for_api_exporting_directory_sec=15
while :
do
    # clear existing generated API schema files to facilitate clear-build environment
    rm -f ${WORK_DIR}/restored_API/*

    # wait for API directory creation
    if [ ! -d "${SHARED_API_DIR}/${MAIN_SERVICE_NAME}" ]; then
        if [ ${wait_for_file_API_counter} == ${wait_for_file_API_limit} ]; then
            echo "API exporting directory has not been served as expected. Abort"
            exit 255
        fi
        let wait_for_file_API_counter=$wait_for_file_API_counter+1
        echo "API exporting directory: ${SHARED_API_DIR}/${MAIN_SERVICE_NAME} - doesn't exist. Another attempt: ${wait_for_file_API_counter}/${wait_for_file_API_limit} - will be made in ${wait_for_api_exporting_directory_sec} seconds."
        sleep ${wait_for_api_exporting_directory_sec} &
        wait $!
        continue
    fi
    ${OPT_DIR}/restore_api_from_pseudo_fs.py ${SHARED_API_DIR} ${MAIN_SERVICE_NAME} ${WORK_DIR}/restored_API

    # wait for API files
    if [ `ls ${WORK_DIR}/restored_API/*.json | wc -l` == 0 ]; then
        if [ ${wait_for_file_API_counter} == ${wait_for_file_API_limit} ]; then
            echo "API exporting directory contains no any JSON data. Abort"
            exit 255
        fi
        let wait_for_file_API_counter=$wait_for_file_API_counter+1
        echo "Nothing was gathered from the API directory: ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}. Please check your exporting API. Another attempt: ${wait_for_file_API_counter}/${wait_for_file_API_limit} - will be made in ${wait_for_api_exporting_directory_sec} seconds."
        sleep ${wait_for_api_exporting_directory_sec} &
        wait $!
        continue
    fi

    rm -f ${WORK_DIR}/rest_api_server/rest_api_server/cgi.py
    cp ${WORK_DIR}/rest_api_server/rest_api_server/cgi_template.py ${WORK_DIR}/rest_api_server/rest_api_server/cgi.py
    ${WORK_DIR}/build_api_cgi.py ${WORK_DIR}/restored_API ${SHARED_API_DIR} ${MAIN_SERVICE_NAME} >> ${WORK_DIR}/rest_api_server/rest_api_server/cgi.py

    cp ${WORK_DIR}/restored_API/index.md  ${WORK_DIR}/rest_api_server/rest_api_server/templates/
    cd ${WORK_DIR}/rest_api_server/
    pipx install -e .

    python -m flask run &
    wait $!
done
