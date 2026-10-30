#!/bin/bash
set -o pipefail

export WORK_DIR=${1}
export INITIAL_PROJECT_LOCATION=${2}
export OPT_DIR=${3}
export SHARED_API_DIR=${4}
export ASSET_MODELS=${5}
export PYTHONPATH="${3}:${3}/modules"

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org
export MICROSERVICE_NAME=ai_agent

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

source "${OPT_DIR}/shell_utils/init_utils.sh"

API_MANAGEMENT_PID=0
declare -A SERVICE_WATCH_PIDS
termination_handler(){
    local exit_status=$?
    trap - SIGHUP SIGQUIT SIGABRT SIGALRM SIGTERM EXIT
    rm -f "${README_FILE_PATH}"
    gracefull_shutdown SERVICE_WATCH_PIDS "${API_MANAGEMENT_PID}"
    exit "${exit_status}"
}
trap "termination_handler" SIGHUP SIGQUIT SIGABRT SIGALRM SIGTERM EXIT

cp -r /API "${WORK_DIR_TMP}" || exit 255
${OPT_DIR}/canonize_internal_api.py "${DEPEND_ON_SERVICES_API_SCHEMA_DIR}" "${MAIN_SERVICE_NAME}/${MICROSERVICE_NAME}" || exit 255

echo "Premature cleanup..."
rm -f "${README_FILE_PATH}"
${OPT_DIR}/api_management.py "${INNER_API_SCHEMA_DIR}|${DEPEND_ON_SERVICES_API_SCHEMA_DIR}" "${MAIN_SERVICE_NAME}" "${SHARED_API_DIR}" &
API_MANAGEMENT_PID=$!
terminate_and_wait "${API_MANAGEMENT_PID}" "Startup API cleanup"
API_MANAGEMENT_PID=0

# The shared inner-API helper loads api_generator.py from its writable work dir.
ln -sf "${WORK_DIR}/api_generator.py" "${WORK_DIR_TMP}/api_generator.py" || exit 255
rm -f "${WORK_DIR_TMP}"/*_exec.sh || exit 255

# Launch internal and command APIs using the service's own user.
launch_command_api_services SERVICE_WATCH_PIDS "${DEPEND_ON_SERVICES_API_SCHEMA_DIR}" "${WORK_DIR_TMP}" "${SHARED_API_DIR}" "${MAIN_SERVICE_NAME}/${MICROSERVICE_NAME}"
launch_inner_api_services SERVICE_WATCH_PIDS "${INNER_API_SCHEMA_DIR}" "${WORK_DIR_TMP}" "${SHARED_API_DIR}" "${README_FILE_PATH}"
${OPT_DIR}/api_management.py "${INNER_API_SCHEMA_DIR}|${DEPEND_ON_SERVICES_API_SCHEMA_DIR}" "${MAIN_SERVICE_NAME}" "${SHARED_API_DIR}" &
API_MANAGEMENT_PID=$!

echo -e "${Blue}Skip checking API dependencies${Color_Off}: ${BBlack}${SKIP_API_DEPS_CHECK}${Color_Off}"
if [ "${SKIP_API_DEPS_CHECK:-}" = false ]; then
    if ! wait_for_unavailable_services "${SHARED_API_DIR}" "${MAIN_SERVICE_NAME}/${MICROSERVICE_NAME}" "${TIMEOUT_FOR_DEPS_CHECK_BEFORE_TERMINATION_SEC}"; then
        echo -e "${BRed}ERROR: As required APIs are missing, the service considered as inoperable. Abort${Color_Off}"
        exit 255
    fi
fi

echo -e "${BBlue}Populating README file...${Color_Off}"
${OPT_DIR}/make_api_readme.py "${INNER_API_SCHEMA_DIR}" | ( umask 0033; cat >> "${README_FILE_PATH}" ) || exit 255

echo -e "${BGreen}The service is ready${Color_Off}"
sleep infinity &
wait $!
