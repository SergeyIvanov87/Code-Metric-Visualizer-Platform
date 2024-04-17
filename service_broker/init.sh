#!/bin/bash

WORK_DIR=${1}
MAIN_IMAGE_ENV_SHARED_LOCATION=${2}
SHARED_API_DIR=${3}

termination_handler(){
   echo "***Stopping"
   exit 0
}

# Setup signal handlers
trap 'termination_handler' SIGTERM

# create API directory and initialize API nodes
mkdir -p ${SHARED_API_DIR}

# TODO: implement NO_NAME_PARM values overriding from `echo exec`
echo "pull origin" > ${SHARED_API_DIR}/api.pmccabe_collector.restapi.org/project/git/0.NO_NAME_PARAM.0
# start crontab
(
set -f
echo -ne "${CRON_REPO_UPDATE_SCHEDULE}\t" > jobs_schedule
${WORK_DIR}/build_schedule_jobs.py ${WORK_DIR}/API ${SHARED_API_DIR} api.pmccabe_collector.restapi.org >> jobs_schedule
)
crontab jobs_schedule
while true; do crond -f -l 0 -d 0; done

sleep infinity &
wait $!
