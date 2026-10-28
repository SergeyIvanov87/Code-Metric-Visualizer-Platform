#!/bin/bash
set -o pipefail

export WORK_DIR=${1}
export INITIAL_PROJECT_LOCATION=${2}
export OPT_DIR=${3}
export SHARED_API_DIR=${4}
export ASSET_MODELS=${5}
export PYTHONPATH="${3}:${3}/modules"

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

export VECTOR_DB_HOST=${VECTORDB_HOST}
export VECTOR_DB_PORT=${VECTORDB_PORT}

# Keep generated files in the writable runtime volume, including when /package
# is a development source mount owned by another user.
export WORK_DIR_TMP=${INITIAL_PROJECT_LOCATION}/generated
mkdir -p "${WORK_DIR_TMP}" || exit 255

export INNER_API_SCHEMA_DIR=${WORK_DIR_TMP}/API
export DEPEND_ON_SERVICES_API_SCHEMA_DIR=${INNER_API_SCHEMA_DIR}/deps

README_FILE_PATH=${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/ai_agent/README-API-STATISTIC.md

# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport WORK_DIR_TMP=${WORK_DIR_TMP}\nexport INITIAL_PROJECT_LOCATION=${INITIAL_PROJECT_LOCATION}\nexport OPT_DIR=${OPT_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME}\nexport INNER_API_SCHEMA_DIR=${INNER_API_SCHEMA_DIR}\nexport DEPEND_ON_SERVICES_API_SCHEMA_DIR=${DEPEND_ON_SERVICES_API_SCHEMA_DIR}\nexport PYTHONPATH=${PYTHONPATH}\nexport VECTOR_DB_HOST=${VECTOR_DB_HOST}\nexport VECTOR_DB_PORT=${VECTOR_DB_PORT}\nexport ASSET_MODELS=${ASSET_MODELS}" > ${WORK_DIR_TMP}/env.sh

source ${OPT_DIR}/shell_utils/init_utils.sh

API_MANAGEMENT_PID=0
PREMATURE_API_MANAGEMENT_PID=0
declare -A SERVICE_WATCH_PIDS
termination_handler(){
    local exit_status=$?
    trap - SIGHUP SIGQUIT SIGABRT SIGALRM SIGTERM EXIT
    rm -f "${README_FILE_PATH}"
    if [ "${PREMATURE_API_MANAGEMENT_PID}" -gt 1 ]; then
        terminate_and_wait "${PREMATURE_API_MANAGEMENT_PID}" "Startup API cleanup"
    fi
    if [ "${API_MANAGEMENT_PID}" -gt 1 ]; then
        gracefull_shutdown SERVICE_WATCH_PIDS "${API_MANAGEMENT_PID}"
    fi
    exit "${exit_status}"
}
trap "termination_handler" SIGHUP SIGQUIT SIGABRT SIGALRM SIGTERM EXIT

cp -r /API "${WORK_DIR_TMP}" || exit 255
${OPT_DIR}/canonize_internal_api.py "${DEPEND_ON_SERVICES_API_SCHEMA_DIR}" "${MAIN_SERVICE_NAME}/ai_agent" || exit 255

echo "Premature cleanup..."
rm -f ${README_FILE_PATH}
${OPT_DIR}/api_management.py "${INNER_API_SCHEMA_DIR}|${DEPEND_ON_SERVICES_API_SCHEMA_DIR}" ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} --deferred-query-root "${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/ai_agent" &
PREMATURE_API_MANAGEMENT_PID=$!
terminate_and_wait "${PREMATURE_API_MANAGEMENT_PID}" "Startup API cleanup"
PREMATURE_API_MANAGEMENT_PID=0


# I use standalone python-based process here to listen to SIGNAL and make PIPEs clearance.
# For any reason, if I just esecute new python process in a trap handler then it will hangs for a long time until executed.
# The default timeour for graceful termination in docker compose exceeds this interval and the container would be killed ungracefully,
# which means no guarantee in PIPEs clearance and hang out processes unblocking
#
# So, to speed up this termination time until being ungracefully killed,
# I just launch this signal listener in background and then resend any signal being catched in the `trap`-handler
# It works as expected
${OPT_DIR}/api_management.py "${INNER_API_SCHEMA_DIR}|${DEPEND_ON_SERVICES_API_SCHEMA_DIR}" ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} --deferred-query-root "${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/ai_agent" &
API_MANAGEMENT_PID=$!

launch_command_api_services SERVICE_WATCH_PIDS ${DEPEND_ON_SERVICES_API_SCHEMA_DIR} ${WORK_DIR_TMP} ${SHARED_API_DIR} "${MAIN_SERVICE_NAME}/ai_agent"

echo -e "${Blue}Skip checking API dependencies${Color_Off}: ${BBlack}${SKIP_API_DEPS_CHECK}${Color_Off}"
if [ "${SKIP_API_DEPS_CHECK:-}" = false ]; then
    if ! wait_for_unavailable_services "${SHARED_API_DIR}" "${MAIN_SERVICE_NAME}/ai_agent" "${TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC}"; then
        echo -e "${BRed}ERROR: As required APIs are missing, the service considered as inoperable. Abort${Color_Off}"
        exit 255
    fi
fi

# TODO consider use launch_inner_api_services!
${OPT_DIR}/build_api_executors.py ${INNER_API_SCHEMA_DIR} ${WORK_DIR} -o ${WORK_DIR_TMP} --overwrite || exit 255
${OPT_DIR}/build_api_services.py ${INNER_API_SCHEMA_DIR} ${WORK_DIR_TMP} -o ${WORK_DIR_TMP}/services || exit 255
${OPT_DIR}/build_api_pseudo_fs.py "${INNER_API_SCHEMA_DIR}" "${SHARED_API_DIR}" || exit 255

launch_fs_api_services SERVICE_WATCH_PIDS "${WORK_DIR_TMP}/services/"

# Probe owned APIs separately: they are not external dependencies. Keep these
# temporary validation schemas outside API/deps and the published API tree.
OWN_API_CHECK_DIR=${WORK_DIR_TMP}/readiness
mkdir -p "${OWN_API_CHECK_DIR}/ai_agent" || exit 255
cp "${INNER_API_SCHEMA_DIR}"/*.json "${DEPEND_ON_SERVICES_API_SCHEMA_DIR}"/*.json "${OWN_API_CHECK_DIR}/ai_agent/" || exit 255
while true; do
    missing_own_api=$(${OPT_DIR}/check_missing_pseudo_fs_from_schema.py "${SHARED_API_DIR}" "${MAIN_SERVICE_NAME}" "${OWN_API_CHECK_DIR}" --timeout 15) || exit 255
    if [ -z "${missing_own_api}" ]; then
        break
    fi
    echo "Waiting for agent API listeners: ${missing_own_api}"
    sleep 0.1 &
    wait $!
done

echo -e "${BBlue}Populating README file...${Color_Off}"
${OPT_DIR}/make_api_readme.py ${INNER_API_SCHEMA_DIR}  | ( umask 0033; cat >> ${README_FILE_PATH} ) || exit 255

echo -e "${BGreen}The service is ready${Color_Off}"
sleep infinity &
wait $!
