#!/bin/bash

export WORK_DIR=${1}
export OPT_DIR=${2}
export PYTHONPATH="${2}:${2}/modules"

export SHARED_API_DIR=${3}
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

source ${OPT_DIR}/shell_utils/init_utils.sh

${OPT_DIR}/canonize_internal_api.py ${WORK_DIR}/API/deps ${MAIN_SERVICE_NAME}/service_broker

declare -A SERVICE_WATCH_PIDS
termination_handler(){
   echo "***Stopping"
   exit 0
}

# Setup signal handlers
trap 'termination_handler' SIGTERM

# create API directory and initialize API nodes
mkdir -p ${SHARED_API_DIR}

# Launch internal API services
${OPT_DIR}/build_common_api_services.py ${WORK_DIR}/API/deps -os ${WORK_DIR}/aux_services -oe ${WORK_DIR}
${OPT_DIR}/build_api_pseudo_fs.py ${WORK_DIR}/API/deps/ ${SHARED_API_DIR}
echo "Run internal API listeners:"
for s in ${WORK_DIR}/aux_services/*.sh; do
    /bin/bash ${s} &
    SERVICE_WATCH_PIDS[${s}]=$!
    echo "${s} has been started, PID ${SERVICE_WATCH_PIDS[${s}]}"
done


echo "Check dependencies..."
get_unavailable_services ${WORK_DIR}/API/deps ANY_SERVICE_UNAVAILABLE_COUNT "${OPT_DIR}/check_missing_pseudo_fs_from_schema.py ${SHARED_API_DIR} ${MAIN_SERVICE_NAME}"
if [ ! -z ${ANY_SERVICE_UNAVAILABLE} ]; then
    echo "ERROR: As required APIs are missing, the service considered as inoperable. Abort"
    exit 255
fi

# TODO: implement NO_NAME_PARM values overriding from `echo exec`
echo "pull origin" > ${SHARED_API_DIR}/api.pmccabe_collector.restapi.org/project/git/0.NO_NAME_PARAM.0
# start crontab
(
set -f
echo -ne "${CRON_REPO_UPDATE_SCHEDULE}\t" > jobs_schedule
${WORK_DIR}/build_schedule_jobs.py ${WORK_DIR}/API ${SHARED_API_DIR} api.pmccabe_collector.restapi.org >> jobs_schedule
)
crontab jobs_schedule

echo "The service is ready"
while true; do crond -f -l 0 -d 0; done

sleep infinity &
wait $!
