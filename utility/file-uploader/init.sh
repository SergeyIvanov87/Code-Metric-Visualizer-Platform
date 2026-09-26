#!/bin/bash
set -u

export WORK_DIR="$1"
export OPT_DIR="$2"
export SHARED_API_DIR="$3"
export PYTHONPATH="${OPT_DIR}:${OPT_DIR}/modules"
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org
export MICROSERVICE_NAME=${MICROSERVICE_NAME:-file-uploader}

source "${OPT_DIR}/shell_utils/init_utils.sh"
"${OPT_DIR}/canonize_internal_api.py" "${WORK_DIR}/API" "${MAIN_SERVICE_NAME}/${MICROSERVICE_NAME}"
"${OPT_DIR}/api_management.py" "${WORK_DIR}/API" "${MAIN_SERVICE_NAME}" "${SHARED_API_DIR}" &
API_MANAGEMENT_PID=$!
declare -A SERVICE_WATCH_PIDS

termination_handler() {
    trap - TERM EXIT
    gracefull_shutdown SERVICE_WATCH_PIDS "${API_MANAGEMENT_PID}"
}
trap termination_handler TERM EXIT

mkdir -p "${SHARED_API_DIR}"
"${OPT_DIR}/build_api_executors.py" "${WORK_DIR}/API" "${WORK_DIR}" -o "${WORK_DIR}"
"${OPT_DIR}/build_api_services.py" "${WORK_DIR}/API" "${WORK_DIR}" -o "${WORK_DIR}/services"
"${OPT_DIR}/build_api_pseudo_fs.py" "${WORK_DIR}/API" "${SHARED_API_DIR}"
launch_fs_api_services SERVICE_WATCH_PIDS "${WORK_DIR}/services/"
wait
