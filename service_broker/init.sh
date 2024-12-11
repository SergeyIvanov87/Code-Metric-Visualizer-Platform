#!/bin/bash

export WORK_DIR=${1}
export OPT_DIR=${2}
export PYTHONPATH="${2}:${2}/modules"

export SHARED_API_DIR=${3}
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport OPT_DIR=${OPT_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh

source ${OPT_DIR}/shell_utils/init_utils.sh

${OPT_DIR}/canonize_internal_api.py ${WORK_DIR}/API/deps ${MAIN_SERVICE_NAME}/service_broker
${OPT_DIR}/api_management.py ${WORK_DIR}/API/deps ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} &
API_MANAGEMENT_PID=$!

declare -A SERVICE_WATCH_PIDS
termination_handler(){
    gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}
    exit 0
}
trap "termination_handler" SIGHUP SIGQUIT SIGABRT SIGKILL SIGALRM SIGTERM

# create API directory and initialize API nodes
mkdir -p ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}

# Launch internal API services
${OPT_DIR}/build_common_api_services.py ${WORK_DIR}/API/deps -os ${WORK_DIR}/aux_services -oe ${WORK_DIR}
${OPT_DIR}/build_api_pseudo_fs.py ${WORK_DIR}/API/deps/ ${SHARED_API_DIR}

launch_fs_api_services SERVICE_WATCH_PIDS "${WORK_DIR}/aux_services"

echo -e "${Blue}Skip checking API dependencies${Color_Off}: ${BBlack}${SKIP_API_DEPS_CHECK}${Color_Off}"
if [ ! -z ${SKIP_API_DEPS_CHECK} ] && [ ${SKIP_API_DEPS_CHECK} == false ]; then
    wait_for_unavailable_services ${SHARED_API_DIR} "${MAIN_SERVICE_NAME}/service_broker" ANY_SERVICE_UNAVAILABLE_COUNT
    if [ ! -z ${ANY_SERVICE_UNAVAILABLE_COUNT} ]; then
        echo -e "{BRed}ERROR: As required APIs are missing, the service considered as inoperable. Abort{Color_Off}"
        gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}
        exit 255
    fi
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

echo -e "${BGreen}The service is ready${Color_Off}"
while true;
do
    crond -f -l 0 -d 0 &
    wait $!
done

sleep infinity &
wait $!
