#!/bin/bash

export WORK_DIR=${1}
export INITIAL_PROJECT_LOCATION=${2}
export SHARED_API_DIR=${3}
export RRD_DATA_STORAGE_DIR=${4}/api.pmccabe_collector.restapi.org

export PYTHONPATH="${WORK_DIR}:${WORK_DIR}/utils:${WORK_DIR}/utils/modules"
UTILS="${WORK_DIR}/utils"
export MODULES="${WORK_DIR}/utils/modules"

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

echo "Create CC API which RRD depends on"
${UTILS}/build_api_pseudo_fs.py /cc_API ${SHARED_API_DIR}
echo "Mock CC API"
find /mnt -regex ".*\\.\\(hpp\\|cpp\\|c\\|h\\)" -type f | /package/pmccabe_visualizer/pmccabe_build.py > /api/${MAIN_SERVICE_NAME}/cc/statistic/GET/result.xml

echo "Run tests:"
for s in ${WORK_DIR}/test_*.py; do
    pytest ${s}
done
