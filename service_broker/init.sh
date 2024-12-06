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
    trap - SIGTERM
    echo "`date +%H:%M:%S:%3N`    ***Shutdown servers***"
    ps -ef
    for server_script_path in "${!SERVICE_WATCH_PIDS[@]}"
    do
        echo "Kill ${server_script_path} by PID: {${SERVICE_WATCH_PIDS[$server_script_path]}}"
        pkill -KILL -e -P ${SERVICE_WATCH_PIDS[$server_script_path]}
        kill -9 ${SERVICE_WATCH_PIDS[$server_script_path]}
        ps -ef
    done
    echo "`date +%H:%M:%S:%3N`    ***Clear pipes****"
    kill -s SIGTERM ${API_MANAGEMENT_PID}
    while true
    do
        kill -s 0 ${API_MANAGEMENT_PID}
        RESULT=$?
        if [ $RESULT == 0 ]; then
            continue
        fi
        break
    done
    echo "`date +%H:%M:%S:%3N`    ***Done****"
    exit 0
}
trap "termination_handler" SIGHUP SIGQUIT SIGABRT SIGKILL SIGALRM SIGTERM

# create API directory and initialize API nodes
mkdir -p ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}

# Launch internal API services
${OPT_DIR}/build_common_api_services.py ${WORK_DIR}/API/deps -os ${WORK_DIR}/aux_services -oe ${WORK_DIR}
${OPT_DIR}/build_api_pseudo_fs.py ${WORK_DIR}/API/deps/ ${SHARED_API_DIR}
echo "Run internal API listeners:"
for s in ${WORK_DIR}/aux_services/*.sh; do
    /bin/bash ${s} &
    SERVICE_WATCH_PIDS[${s}]=$!
    echo "${s} has been started, PID ${SERVICE_WATCH_PIDS[${s}]}"
done


echo "Skip checking  API dependencies: ${SKIP_API_DEPS_CHECK}"
if [ ! -z ${SKIP_API_DEPS_CHECK} ] && [ ${SKIP_API_DEPS_CHECK} == false ]; then
    get_unavailable_services ${WORK_DIR}/API/deps ANY_SERVICE_UNAVAILABLE_COUNT "${OPT_DIR}/check_missing_pseudo_fs_from_schema.py ${SHARED_API_DIR} ${MAIN_SERVICE_NAME}"
    if [ ! -z ${ANY_SERVICE_UNAVAILABLE} ]; then
        echo "ERROR: As required APIs are missing, the service considered as inoperable. Abort"
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

echo "The service is ready"
while true;
do
    crond -f -l 0 -d 0 &
    wait $!
done

sleep infinity &
wait $!
