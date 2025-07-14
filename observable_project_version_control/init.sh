#!/bin/bash

export WORK_DIR=${1}
export INITIAL_PROJECT_LOCATION=${2}
export OPT_DIR=${3}
export PYTHONPATH="${3}:${3}/modules"
export SHARED_API_DIR=${4}
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

README_FILE_PATH=${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/project/README-API-VCS.md

# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport INITIAL_PROJECT_LOCATION=${INITIAL_PROJECT_LOCATION}\nexport OPT_DIR=${OPT_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh

source ${OPT_DIR}/shell_utils/init_utils.sh

# I use standalone python-based process here to listen to SIGNAL and make PIPEs clearance.
# For any reason, if I just esecute new python process in a trap handler then it will hangs for a long time until executed.
# The default timeour for graceful termination in docker compose exceeds this interval and the container would be killed ungracefully,
# which means no guarantee in PIPEs clearance and hang out processes unblocking
#
# So, to speed up this termination time until being ungracefully killed,
# I just launch this signal listener in background and then resend any signal being catched in the `trap`-handler
# It works as expected
${OPT_DIR}/api_management.py ${WORK_DIR}/API/ ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} &
API_MANAGEMENT_PID=$!

declare -A SERVICE_WATCH_PIDS
termination_handler(){
    trap - SIGTERM
    rm -f ${README_FILE_PATH}
    gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}
    exit 0
}
trap "termination_handler" SIGHUP SIGQUIT SIGABRT SIGKILL SIGALRM SIGTERM

# allow pmccabe_collector to access reposiroty
git -C ${INITIAL_PROJECT_LOCATION} pull || git clone ${PROJECT_URL} -b ${PROJECT_BRANCH} ${INITIAL_PROJECT_LOCATION}
if [ $? -ne 0 ]; then
    echo "Cannot pull project ${PROJECT_URL} by branch: ${PROJECT_BRANCH} into location: ${INITIAL_PROJECT_LOCATION}"
    exit -1
fi

# create API directory and initialize API nodes
mkdir -p ${SHARED_API_DIR}
${OPT_DIR}/build_api_executors.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}
${OPT_DIR}/build_api_services.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}/services
${OPT_DIR}/build_api_pseudo_fs.py ${WORK_DIR}/API ${SHARED_API_DIR}
${OPT_DIR}/make_api_readme.py ${WORK_DIR}/API > ${README_FILE_PATH}
chmod g+rw ${README_FILE_PATH}

launch_fs_api_services SERVICE_WATCH_PIDS "${WORK_DIR}/services/"

echo -e "${BGreen}The service is ready${Color_Off}"
sleep infinity &
wait $!
