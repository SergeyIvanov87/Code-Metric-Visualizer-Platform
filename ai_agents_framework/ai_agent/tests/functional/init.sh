#!/bin/bash

export WORK_DIR=${1}
export SHARED_API_DIR=${2}

cat > "env.sh" <<EOF
export WORK_DIR=${WORK_DIR}
export SHARED_API_DIR=${SHARED_API_DIR}
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org
export PYTHONPATH="${WORK_DIR}:${WORK_DIR}/utils:${WORK_DIR}/utils/modules"
export UTILS="${WORK_DIR}/utils"
export OPT_DIR=${UTILS}
export MODULES="${WORK_DIR}/utils/modules"
export TESTED_SERVICE_NAME="ai_agent"

export RAG_DB_HOST=${TEST_RAG_DB_HOST}
export RAG_DB_PORT=${TEST_RAG_DB_PORT}
EOF

source "env.sh"
${UTILS}/canonize_internal_api.py ${WORK_DIR}/API/deps ${MAIN_SERVICE_NAME}/${TESTED_SERVICE_NAME}

# copy APIs (command & internal) into designated directory /API
# in order to allow tests_inner_api to test its inner API.
# Do not push something other into /API!
mkdir -p -m 777 /API
cp -r ${WORK_DIR}/API/* /API/

source ${UTILS}/shell_utils/init_utils.sh

API_MANAGEMENT_PID=0
declare -A SERVICE_WATCH_PIDS
termination_handler(){
    rm -f ${README_FILE_PATH}
    gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}
    exit 0
}
trap "termination_handler" SIGHUP SIGQUIT SIGABRT SIGKILL SIGALRM SIGTERM EXIT

echo "Generate Mock API"
# Own command API, as we must not launch own command services from service_broker
mkdir -p -m 777 bk_own_API
mv ${WORK_DIR}/API/*.json bk_own_API/
mv ${WORK_DIR}/API/deps/all_dependencies.json all_dependencies.json
mv ${WORK_DIR}/API/deps/unmet_dependencies.json unmet_dependencies.json
mkdir -p -m 777 ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}

# launch all the dependencies of the tested service to allow the service to find them,
# so that the service will be able to set up
API_MANAGEMENT_SCHEMA_DIRS=""
for deps_service in ${WORK_DIR}/API/deps/*; do
    echo "Mock API from ${deps_service}"
    if [ -d ${deps_service} ];
    then
        echo "Mocking..."
        API_MANAGEMENT_SCHEMA_DIRS="${API_MANAGEMENT_SCHEMA_DIRS:+${API_MANAGEMENT_SCHEMA_DIRS}|}${deps_service}"
        # Do not use launch_inner_services() as it doesn't suppose sequencial usage in cycle
        ${UTILS}/build_api_executors.py ${deps_service} ${WORK_DIR} -o ${WORK_DIR}
        ${UTILS}/build_api_services.py ${deps_service} ${WORK_DIR} -o ${WORK_DIR}/services
        ${UTILS}/build_api_pseudo_fs.py ${deps_service} ${SHARED_API_DIR}
    fi
done

for s in ${WORK_DIR}/services/*_server.sh; do
    ${s} ${UTILS} &
    SERVICE_WATCH_PIDS[${s}]=$!
    echo "${s} has been started"
done

${UTILS}/api_management.py "${API_MANAGEMENT_SCHEMA_DIRS}" ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} &
API_MANAGEMENT_PID=$!

# Now the tested service  must have started before we continue with tests
echo -e "Wait for ${TESTED_SERVICE_NAME} broker starting"
wait_for_unavailable_services ${SHARED_API_DIR} "${MAIN_SERVICE_NAME}/${TESTED_SERVICE_NAME}"
if [ $? -ne 0 ]; then
    echo -e "${BRed}ERROR: As required APIs are missing, the service considered as inoperable. Abort${Color_Off}"
    gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}
    exit 255
fi

echo "Run tests:"
RET=0
cp -r ${WORK_DIR}/rag_data /api/api.pmccabe_collector.restapi.org/
for s in ${WORK_DIR}/test_*.py; do
    pytest -svv ${s}
    VAL=$?
    if [ $VAL != 0 ]
    then
        RET=$VAL
    fi
done

mv bk_own_API/*.json ${WORK_DIR}/API/
cp -r /API/deps ${WORK_DIR}/API/

gracefull_shutdown SERVICE_WATCH_PIDS ${API_MANAGEMENT_PID}
#rm -rf ${SHARED_API_DIR}/*
if [ $EXIT_ONCE_DONE == true ]; then
    exit $RET
fi

echo "wait for termination: ${RET}"
sleep infinity &
wait $!
exit $RET
