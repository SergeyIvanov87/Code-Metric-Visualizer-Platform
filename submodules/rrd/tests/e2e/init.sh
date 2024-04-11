#!/bin/bash

export WORK_DIR=${1}
export INITIAL_PROJECT_LOCATION=${2}
export SHARED_API_DIR=${3}
export RRD_DATA_STORAGE_DIR=${4}/api.pmccabe_collector.restapi.org

export UTILS="/main_image_env"

# TODO temporary solution sleep 60:
# this container must     depends_on: - rrd_analytic
# unless issue #34 closed, it can't be done, because rrd_analytic depend on cyclomatic complexity and requires for some shared utils files in it
sleep 10

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

echo "Create CC API which RRD depends on"
/main_image_env/build_api_pseudo_fs.py /cc_API ${SHARED_API_DIR}

echo "Run tests:"
for s in ${WORK_DIR}/test_*.py; do
    pytest ${s}
done
