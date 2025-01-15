#!/bin/bash

export WORK_DIR=${1}
export SHARED_API_DIR=${2}
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

export PYTHONPATH="${WORK_DIR}:${WORK_DIR}/utils:${WORK_DIR}/utils/modules"
UTILS="${WORK_DIR}/utils"
export OPT_DIR="${WORK_DIR}/utils"
export MODULES="${WORK_DIR}/utils/modules"

echo -e "export WORK_DIR=${WORK_DIR}\nexport UTILS=${UTILS}\nexport OPT_DIR=${OPT_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME}\nexport UPSTREAM_SERVICE=${UPSTREAM_SERVICE}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh


export FLASK_RUN_HOST=0.0.0.0
export FLASK_RUN_PORT=80
flask --app stub_downstream_http_server --debug run


if [ $EXIT_ONCE_DONE == true ]; then exit $RET; fi

echo "wait for termination"
sleep infinity &
wait $!
exit $RET
