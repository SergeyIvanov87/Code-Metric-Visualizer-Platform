#!/bin/bash

WORK_DIR=${1}
MAIN_IMAGE_ENV_SHARED_LOCATION=${2}
SHARED_API_DIR=${3}

# start crontab
echo "${CRON_REPO_UPDATE_SCHEDULE} cd ${INITIAL_PROJECT_LOCATION} && echo \"Hello World\"" > daily_pull
crontab daily_pull
crond -b -l 0 -d 0

# create API directory and initialize API nodes
mkdir -p ${SHARED_API_DIR}
#${MAIN_IMAGE_ENV_SHARED_LOCATION}/build_api_executors.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}
#${MAIN_IMAGE_ENV_SHARED_LOCATION}/build_api_services.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}/services
#${MAIN_IMAGE_ENV_SHARED_LOCATION}/build_api_pseudo_fs.py ${WORK_DIR}/API ${SHARED_API_DIR}

echo "run API listeners:"
for s in ${WORK_DIR}/services/*.sh; do
    ${s} ${MAIN_IMAGE_ENV_SHARED_LOCATION} &
    echo "${s} has been started"
done

sleep infinity
