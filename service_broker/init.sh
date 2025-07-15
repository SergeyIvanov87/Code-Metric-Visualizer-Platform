#!/bin/bash

export WORK_DIR=${1}
export OPT_DIR=${2}
export PYTHONPATH="${2}:${2}/modules"

export SHARED_API_DIR=${3}
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

export DEPEND_ON_SERVICES_API_SCHEMA_DIR=${WORK_DIR}/API/deps
export INNER_API_SCHEMA_DIR=${WORK_DIR}/API

# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport OPT_DIR=${OPT_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME}\nexport INNER_API_SCHEMA_DIR=${INNER_API_SCHEMA_DIR}\nexport DEPEND_ON_SERVICES_API_SCHEMA_DIR=${DEPEND_ON_SERVICES_API_SCHEMA_DIR}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh

# start & activate syslogd
doas -u root rc-status
doas -u root touch /run/openrc/softlevel
doas -u root rc-service syslog start
doas -u root rc-service syslog status


source ${OPT_DIR}/shell_utils/color_codes.sh
if [ -z ${MICROSERVICE_NAME} ]; then
    echo -e "{BRed}ERROR: Please specify env/arg MICROSERVICE_NAME. Abort${Color_Off}"
    exit 255
fi
echo -e "${BGreen}Initializing: ${MICROSERVICE_NAME}...${Color_Off}"

source ${OPT_DIR}/shell_utils/init_utils.sh
API_MANAGEMENT_PID=0
declare -A SERVICE_WATCH_PIDS
termination_handler(){
    gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}
    exit 0
}
trap "termination_handler" SIGHUP SIGQUIT SIGABRT SIGKILL SIGALRM SIGTERM

# create API directory and initialize API nodes
mkdir -p -m 777 ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}

# Launch internal API services
launch_command_api_services SERVICE_WATCH_PIDS ${DEPEND_ON_SERVICES_API_SCHEMA_DIR} ${WORK_DIR} ${SHARED_API_DIR} "${MAIN_SERVICE_NAME}/${MICROSERVICE_NAME}"
${OPT_DIR}/api_management.py ${DEPEND_ON_SERVICES_API_SCHEMA_DIR} ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} &
API_MANAGEMENT_PID=$!

echo -e "${Blue}Skip checking API dependencies${Color_Off}: ${BBlack}${SKIP_API_DEPS_CHECK}${Color_Off}"
if [ ! -z ${SKIP_API_DEPS_CHECK} ] && [ ${SKIP_API_DEPS_CHECK} == false ]; then
    wait_for_unavailable_services ${SHARED_API_DIR} "${MAIN_SERVICE_NAME}/${MICROSERVICE_NAME}" ANY_SERVICE_UNAVAILABLE_COUNT ${TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC}
    if [ ! -z ${ANY_SERVICE_UNAVAILABLE_COUNT} ]; then
        echo -e "${BRed}ERROR: As required APIs are missing, the service considered as inoperable. Abort${Color_Off}"
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
${WORK_DIR}/build_schedule_jobs.py ${INNER_API_SCHEMA_DIR} ${SHARED_API_DIR} api.pmccabe_collector.restapi.org >> jobs_schedule
)

doas -u root crontab jobs_schedule

echo -e "${BGreen}The service is ready${Color_Off}"
while true;
do
    doas -u root crond -f -l 0 -d 0 &
    wait $!
done

sleep infinity &
wait $!
