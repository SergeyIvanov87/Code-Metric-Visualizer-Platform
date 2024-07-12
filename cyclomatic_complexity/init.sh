#!/bin/bash

export WORK_DIR=${1}
export INITIAL_PROJECT_LOCATION=${2}
export OPT_DIR=${3}
export SHARED_API_DIR=${4}
export PYTHONPATH="${3}:${3}/modules"

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

README_FILE_PATH=${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/README-API-STATISTIC.md

# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport INITIAL_PROJECT_LOCATION=${INITIAL_PROJECT_LOCATION}\nexport OPT_DIR=${OPT_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh

declare -A SERVICE_WATCH_PIDS
termination_handler(){
    trap - SIGTERM
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
trap termination_handler SIGTERM

# create API directory and initialize API nodes
mkdir -p ${SHARED_API_DIR}
TMPDIR=$(mktemp -d --tmpdir=${SHARED_API_DIR})
if [ $? -ne 0 ]; then echo "Cannot create ${SHARED_API_DIR}. Please check access rights to the VOLUME '/api' and grant the container all of them"; exit -1; fi
rm -rf $TMPDIR

${OPT_DIR}/build_api_executors.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}
${OPT_DIR}/build_api_services.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}/services
${OPT_DIR}/build_api_pseudo_fs.py ${WORK_DIR}/API ${SHARED_API_DIR}
${OPT_DIR}/make_api_readme.py ${WORK_DIR}/API > ${README_FILE_PATH}

# TODO think about necessity in creating any pivot metrics
# There are few disadvantages about it:
# 1) for a large project it will introduce latency in container starting, because
# a lot of files requires more time to build statistic
# 2) It's not possible to pass an universal argument to configure source files lists
# for colelcting statistics and to specify any other precision parameters
# 3) taking into account the previous points the collected statistics might not apt
# for durther holistic analysis
#
# Conclusion: do not attempt to call any API commands to build statistic here in init.sh

echo "run API listeners:"
for s in ${WORK_DIR}/services/*.sh; do
    ${s} ${OPT_DIR} &
    SERVICE_WATCH_PIDS[${s}]=$!
    echo "${s} has been started, PID ${SERVICE_WATCH_PIDS[${s}]}"
done

sleep infinity &
wait $!
termination_handler()
