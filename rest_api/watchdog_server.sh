#!/bin/sh

let wait_for_file_API_counter=0
let wait_for_file_API_limit=4
let wait_for_api_exporting_directory_sec=15
while :
do
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

    # clear existing generated API schema files to facilitate clear-build environment
    rm -f ${WORK_DIR}/restored_API/*
    ${OPT_DIR}/restore_api_from_pseudo_fs.py ${SHARED_API_DIR} ${MAIN_SERVICE_NAME} ${WORK_DIR}/restored_API

    # wait for API files
    if [ `ls ${WORK_DIR}/restored_API/*.json | wc -l` == 0 ]; then
        if [ ${wait_for_file_API_counter} == ${wait_for_file_API_limit} ]; then
            echo "API exporting directory contains no JSON data. Abort"
            exit 255
        fi
        let wait_for_file_API_counter=$wait_for_file_API_counter+1
        echo "Nothing was gathered from the API directory: ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}. Please check your exporting API. Another attempt: ${wait_for_file_API_counter}/${wait_for_file_API_limit} - will be made in ${wait_for_api_exporting_directory_sec} seconds."
        sleep ${wait_for_api_exporting_directory_sec} &
        wait $!
        continue
    fi

    echo "Generate REST_API CGIs from imported API entry point"
    rm -f ${WORK_DIR}/rest_api_server/rest_api_server/cgi.py
    cp ${WORK_DIR}/rest_api_server/rest_api_server/cgi_template.py ${WORK_DIR}/rest_api_server/rest_api_server/cgi.py

    rm -f ${WORK_DIR}/restored_API/index.md
    ${WORK_DIR}/build_api_cgi.py ${WORK_DIR}/restored_API ${SHARED_API_DIR} ${MAIN_SERVICE_NAME} >> ${WORK_DIR}/rest_api_server/rest_api_server/cgi.py

    if [ ! -f ${WORK_DIR}/restored_API/index.md ]; then
        echo "Can't find API README from'${WORK_DIR}/restored_API/index.md' - probably filesystem API is inconsistent. REST_API server won't serve any request and will be stopped"
        exit 255
    fi
    cp ${WORK_DIR}/restored_API/index.md  ${WORK_DIR}/rest_api_server/rest_api_server/templates/
    cd ${WORK_DIR}/rest_api_server/

    echo "Start REST_API server"
    pipx install -e .

    python -m flask run &
    wait $!
done
