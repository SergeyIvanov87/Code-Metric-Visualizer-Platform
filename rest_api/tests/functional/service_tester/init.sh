#!/bin/bash

export WORK_DIR=${1}
export SHARED_API_DIR=${2}

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org
export PYTHONPATH="${WORK_DIR}:${WORK_DIR}/utils:${WORK_DIR}/utils/modules"
UTILS="${WORK_DIR}/utils"
export MODULES="${WORK_DIR}/utils/modules"

# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh


# clear existing generated API schema files to facilitate clear-build environment
rm -fr ${WORK_DIR}/restored_API
mkdir -p ${WORK_DIR}/restored_API
${UTILS}/restore_api_from_pseudo_fs.py ${SHARED_API_DIR} ${MAIN_SERVICE_NAME} ${WORK_DIR}/restored_API

echo "Wait until service started"
let wait_for_counter=0
let wait_for_limit=12
let wait_for_sec=10
SERVICE=http://rest_api:5000
while true
do
    curl -I -s -o /dev/null ${SERVICE}
    if [ $? -eq 0 ];
    then
       break
    else
        if [ ${wait_for_counter} == ${wait_for_limit} ]; then
            echo "${SERVICE} has not been started. Abort"
            exit 255
        fi
        let wait_for_counter=$wait_for_counter+1
        echo "${SERVICE} is offline. Another attempt: ${wait_for_counter}/${wait_for_limit} - will be made in ${wait_for_sec} seconds."
        sleep ${wait_for_sec} &
        wait $!
        continue
    fi
done

# waiting until all API events are handled by REST_API service
sleep 15

# Check if service is up once again
let wait_for_counter=0
while true
do
    curl -I -s -o /dev/null ${SERVICE}
    if [ $? -eq 0 ];
    then
       break
    else
        if [ ${wait_for_counter} == ${wait_for_limit} ]; then
            echo "${SERVICE} has not been started. Abort"
            exit 255
        fi
        let wait_for_counter=$wait_for_counter+1
        echo "${SERVICE} is offline. Another attempt: ${wait_for_counter}/${wait_for_limit} - will be made in ${wait_for_sec} seconds."
        sleep ${wait_for_sec} &
        wait $!
        continue
    fi
done


echo "Run tests:"
RET=0
cp ${WORK_DIR}/data/portal.json ${WORK_DIR}/restored_API/portal.json
for s in ${WORK_DIR}/test_*.py; do
    pytest -rxXs ${s}
    VAL=$?
    if [ $VAL != 0 ]
    then
        RET=$VAL
    fi
done

if [ $EXIT_ONCE_DONE == true ]; then exit $RET; fi

echo "wait for termination"
sleep infinity &
wait $!
exit $RET
