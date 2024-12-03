#!/bin/bash

export WORK_DIR=${1}
export OPT_DIR=${2}
export PYTHONPATH="${2}:${2}/modules"

export SHARED_API_DIR=${3}
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

${OPT_DIR}/canonize_internal_api.py ${WORK_DIR}/API/deps ${MAIN_SERVICE_NAME}/service_broker

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
