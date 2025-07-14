#!/bin/bash

export WORK_DIR=${1}
export INITIAL_PROJECT_LOCATION=${2}
export OPT_DIR=${3}
export SHARED_API_DIR=${4}
export PYTHONPATH="${3}:${3}/modules"

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

export INNER_API_SCHEMA_DIR=${WORK_DIR}/API

README_FILE_PATH=${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/README-API-STATISTIC.md

# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport INITIAL_PROJECT_LOCATION=${INITIAL_PROJECT_LOCATION}\nexport OPT_DIR=${OPT_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport INNER_API_SCHEMA_DIR=${INNER_API_SCHEMA_DIR}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh

# TODO maybe should rely on build_seudo_fs.py?? as it create an entire  chain of directories
mkdir -p -m 777 ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}
if [ $? -ne 0 ]; then echo "Cannot create ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}. Please check access rights to the VOLUME '/api' and grant the container all of them"; exit -1; fi

source ${OPT_DIR}/shell_utils/init_utils.sh

# I use standalone python-based process here to listen to SIGNAL and make PIPEs clearance.
# For any reason, if I just esecute new python process in a trap handler then it will hangs for a long time until executed.
# The default timeour for graceful termination in docker compose exceeds this interval and the container would be killed ungracefully,
# which means no guarantee in PIPEs clearance and hang out processes unblocking
#
# So, to speed up this termination time until being ungracefully killed,
# I just launch this signal listener in background and then resend any signal being catched in the `trap`-handler
# It works as expected
${OPT_DIR}/api_management.py ${INNER_API_SCHEMA_DIR} ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} &
API_MANAGEMENT_PID=$!

declare -A SERVICE_WATCH_PIDS
termination_handler(){
    trap - SIGTERM
    rm -f ${README_FILE_PATH}
    gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}
    exit 0
}
trap "termination_handler" SIGHUP SIGQUIT SIGABRT SIGKILL SIGALRM SIGTERM

# create API directory and initialize API nodes
mkdir -p ${SHARED_API_DIR}
TMPDIR=$(mktemp -d --tmpdir=${SHARED_API_DIR})
if [ $? -ne 0 ]; then echo "Cannot create ${SHARED_API_DIR}. Please check access rights to the VOLUME '/api' and grant the container all of them"; exit -1; fi
rm -rf $TMPDIR

# TODO consider use launch_inner_api_services!
${OPT_DIR}/build_api_executors.py ${INNER_API_SCHEMA_DIR} ${WORK_DIR} -o ${WORK_DIR}
${OPT_DIR}/build_api_services.py ${INNER_API_SCHEMA_DIR} ${WORK_DIR} -o ${WORK_DIR}/services
${OPT_DIR}/build_api_pseudo_fs.py ${INNER_API_SCHEMA_DIR} ${SHARED_API_DIR}
${OPT_DIR}/make_api_readme.py ${INNER_API_SCHEMA_DIR} > ${README_FILE_PATH}
chmod g+rw ${README_FILE_PATH}

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

launch_fs_api_services SERVICE_WATCH_PIDS "${WORK_DIR}/services/"

echo -e "${BGreen}The service is ready${Color_Off}"
sleep infinity &
wait $!
