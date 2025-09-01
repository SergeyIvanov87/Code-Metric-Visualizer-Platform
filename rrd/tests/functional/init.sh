#!/bin/bash

export WORK_DIR=${1}
export INITIAL_PROJECT_LOCATION=${2}
export SHARED_API_DIR=${3}
export RRD_DATA_STORAGE_DIR=${4}/api.pmccabe_collector.restapi.org

export PYTHONPATH="${WORK_DIR}:${WORK_DIR}/utils:${WORK_DIR}/utils/modules"
UTILS="${WORK_DIR}/utils"
export OPT_DIR=${WORK_DIR}/utils
export MODULES="${WORK_DIR}/utils/modules"

export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

echo -e "export WORK_DIR=${WORK_DIR}\nexport UTILS=${UTILS}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport RRD_DATA_STORAGE_DIR=${RRD_DATA_STORAGE_DIR}\nexport MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh

rm -rf ${RRD_DATA_STORAGE_DIR}
mkdir -p -m 777 ${RRD_DATA_STORAGE_DIR}

# inject test files into project directory
test_files=(/package/test_data/*.cpp)
for f in "${test_files[@]}"; do
    cp ${f} ${INITIAL_PROJECT_LOCATION}/
done

MICROSERVICE_NAME_TO_TEST=rrd_analytic
${UTILS}/canonize_internal_api.py /API/deps ${MAIN_SERVICE_NAME}/${MICROSERVICE_NAME_TO_TEST}

echo "Create CC API which RRD depends on"
${UTILS}/build_api_pseudo_fs.py /API/deps/cyclomatic_complexity ${SHARED_API_DIR}

echo "Mock CC API for standalone functional tests only"
rm -f ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/statistic/GET/result.xml_fake_data
fake_statistic_data_result=${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/statistic/GET/result.xml_fake_data
find ${INITIAL_PROJECT_LOCATION} -regex ".*\\.\\(hpp\\|cpp\\|c\\|h\\)" -type f | /package/pmccabe_visualizer/pmccabe_build.py > ${fake_statistic_data_result}
real_statistic_pipe_out=${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/statistic/GET/result.xml_${RRD_TESTABLE_CONTAINER_HOSTNAME}
if [ -e ${real_statistic_pipe_out} ]; then
    rm -f ${real_statistic_pipe_out}
fi
mkfifo -m 644 ${real_statistic_pipe_out}

real_main_statistic_pipe_out=${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/statistic/GET/result.xml
if [ -e ${real_main_statistic_pipe_out} ]; then
    rm -f ${real_main_statistic_pipe_out}
fi
mkfifo -m 644 ${real_main_statistic_pipe_out}

real_statistic_pipe_in=${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/statistic/GET/exec
if [ -e ${real_statistic_pipe_in} ]; then
    rm -f ${real_statistic_pipe_in}
fi
mkfifo -m 622 ${real_statistic_pipe_in}
#echo 0 > ${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/cc/statistic/GET/exec
echo "Ready to server Mock CC API"
(
while :
do
    CMD=`cat ${real_statistic_pipe_in}`
    readarray -t IN_SERVER_REQUEST_ARGS <<< "${CMD}"
    KEEP_ALIVE_VALUE=
    unset KEEP_ALIVE_VALUE
    for arg in ${IN_SERVER_REQUEST_ARGS[@]}
    do
        if [[ "${arg}" = "API_KEEP_ALIVE_CHECK"* ]];
        then
            readarray -d '=' -t AVP <<< "${arg}"
            KEEP_ALIVE_VALUE=${AVP[1]}
            break
        fi
    done
    if [ ! -z ${KEEP_ALIVE_VALUE} ]; then
        echo "KEEP_ALIVE_PROBE request: ${KEEP_ALIVE_VALUE}"
        echo -n "${KEEP_ALIVE_VALUE}" > ${real_statistic_pipe_out}
        continue
    fi
    ############################################################
    echo "`date +%H:%M:%S:%3N`    START:${CMD}"
    echo "`date +%H:%M:%S:%3N`    MOCK FINISH: ${real_statistic_pipe_out}"
    cat ${fake_statistic_data_result} > ${real_statistic_pipe_out}
    echo "`date +%H:%M:%S:%3N`    MOCK CONSUMED: ${real_statistic_pipe_out}"
done
) &
WATCH_PID=$!

source ${OPT_DIR}/shell_utils/init_utils.sh
gracefull_shutdown_handler(){
    # remove test files from project directory
    for f in ${test_files[@]}; do
        fname=`basename ${f}`
        rm -f ${INITIAL_PROJECT_LOCATION}/${fname}
    done

    kill -15 ${WATCH_PID}
    wait ${WATCH_PID}
    rm -f ${real_statistic_pipe_in}
    rm -f ${real_statistic_pipe_out}
    rm -f ${real_main_statistic_pipe_out}
    echo "Final API fs snapshot, result ${RET}:"
    ls -laR ${SHARED_API_DIR}
}

# If we continue with tests, rrd_analytic must have been started
echo -e "Wait for rrd starting"
wait_for_unavailable_services ${SHARED_API_DIR} "${MAIN_SERVICE_NAME}/${MICROSERVICE_NAME_TO_TEST}"
if [ $? -ne 0 ]; then
    echo -e "${BRed}ERROR: As required APIs are missing, the service considered as inoperable. Abort${Color_Off}"
    gracefull_shutdown_handler
    exit 255
fi

echo "Run tests:"
RET=0
for s in ${WORK_DIR}/test_*.py; do
    # '-s' argument repeals console output capturing by pytest, which allow us
    # to use heartbeat mechanism to keep `test_aggregator` alive during
    # long test cases execution (likewise RRDs collecting)
    pytest -s ${s}
    VAL=$?
    if [ $VAL != 0 ]
    then
        RET=$VAL
    fi
    #echo "API fs snapshot after test execution: ${s}, result: ${VAL}"
    #ls -laR ${SHARED_API_DIR}
done

gracefull_shutdown_handler

if [ $EXIT_ONCE_DONE == true ]; then exit $RET; fi

echo "wait for termination"
sleep infinity &
wait $!
exit $RET
