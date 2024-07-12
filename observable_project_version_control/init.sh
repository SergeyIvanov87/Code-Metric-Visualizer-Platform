#!/bin/bash

export WORK_DIR=${1}
export INITIAL_PROJECT_LOCATION=${2}
export OPT_DIR=${3}
export PYTHONPATH="${3}:${3}/modules"
export SHARED_API_DIR=${4}

declare -A SERVICE_WATCH_PIDS
termination_handler(){
    trap - SIGHUP SIGQUIT SIGABRT SIGKILL SIGALRM SIGTERM
    echo "***Shutdown servers***"
    ps -ef
    rm -f ${README_FILE_PATH}
    for server_script_path in "${!SERVICE_WATCH_PIDS[@]}"
    do
        echo "Kill ${server_script_path} by PID: {${SERVICE_WATCH_PIDS[$server_script_path]}}"
        pkill -KILL -e -P ${SERVICE_WATCH_PIDS[$server_script_path]}
        kill -9 ${SERVICE_WATCH_PIDS[$server_script_path]}
        ps -ef
    done
    echo "***Clear pipes****"
    ${OPT_DIR}/renew_pseudo_fs_pipes.py ${WORK_DIR}/API "server" ${SHARED_API_DIR}
    ${OPT_DIR}/renew_pseudo_fs_pipes.py ${WORK_DIR}/API "client" ${SHARED_API_DIR}

    exit 0
}

# Setup signal handlers
trap 'termination_handler' SIGHUP SIGQUIT SIGABRT SIGKILL SIGALRM SIGTERM

# allow pmccabe_collector to access reposiroty
git clone ${PROJECT_URL} -b ${PROJECT_BRANCH} ${INITIAL_PROJECT_LOCATION}

# create API directory and initialize API nodes
mkdir -p ${SHARED_API_DIR}
${OPT_DIR}/build_api_executors.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}
${OPT_DIR}/build_api_services.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}/services
${OPT_DIR}/build_api_pseudo_fs.py ${WORK_DIR}/API ${SHARED_API_DIR}
${OPT_DIR}/make_api_readme.py ${WORK_DIR}/API > ${SHARED_API_DIR}/api.pmccabe_collector.restapi.org/project/README-API-STATISTIC.md

echo "run API listeners:"
for s in ${WORK_DIR}/services/*.sh; do
    ${s} &
    SERVICE_WATCH_PIDS[${s}]=$!
    echo "${s} has been started, PID ${SERVICE_WATCH_PIDS[${s}]}"
done

sleep infinity
