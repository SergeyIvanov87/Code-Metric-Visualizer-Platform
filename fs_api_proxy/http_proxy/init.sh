#!/bin/bash

export WORK_DIR=${1}
export OPT_DIR=${2}
export PYTHONPATH="${2}:${2}/modules"
export SHARED_API_DIR=${3}
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport OPT_DIR=${OPT_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh

source ${OPT_DIR}/shell_utils/init_utils.sh

echo -e "${Blue}Proxy UPSTREAM_SERVICE: ${BBlue}${UPSTREAM_SERVICE}${Blue}, DOWNSTREAM_SERVICE: ${BBlue}${DOWNSTREAM_SERVICE}${Blue}, DOWNSTREAM_SERVICE_NETWORK_ADDR: ${BBlue}${DOWNSTREAM_SERVICE_NETWORK_ADDR}${Color_Off}"
if [ -z ${UPSTREAM_SERVICE} ]; then
    echo -e "${BRed}ERROR:${Color_Off}The environment variable ${BRed}UPSTREAM_SERVICE${Color_Off} is not configured. Cannot start without proxying anything"
    exit 255
fi

if [ -z ${DOWNSTREAM_SERVICE} ]; then
    echo -e "${BRed}ERROR:${Color_Off}The environment variable ${BRed}DOWNSTREAM_SERVICE${Color_Off} is not configured. Cannot start without proxying anything"
    exit 255
fi

if [ -z ${DOWNSTREAM_SERVICE_NETWORK_ADDR} ]; then
    echo -e "${BRed}ERROR:${Color_Off}The environment variable ${BRed}DOWNSTREAM_SERVICE_NETWORK_ADDR${Color_Off} is not configured. Cannot start without proxying anything"
    exit 255
fi

echo -e "${Blue}Waiting for UPSTREAM_SERVICE: ${BBlue}${UPSTREAM_SERVICE}${Color_Off}"
SESSION_ID="`hostname`_watchdog"
pipe_in="${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/${UPSTREAM_SERVICE}/unmet_dependencies/GET/exec"
pipe_out="${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/${UPSTREAM_SERVICE}/unmet_dependencies/GET/result.json_${SESSION_ID}"

#while [ ! -p ${pipe_in} ]; do sleep 0.1; echo "waiting for pipe IN: ${pipe_in}"; done
#echo "SESSION_ID=${SESSION_ID} --service=${DOWNSTREAM_SERVICE}"> ${pipe_in}
#while [ ! -p ${pipe_out} ]; do sleep 0.1; echo "waiting for pipe OUT: ${pipe_out}"; done
#PROXYING_API_QUERIES=`cat ${pipe_out}`

#echo "PROXYING_API_QUERIES: ${PROXYING_API_QUERIES}"
#if [ -z "${PROXYING_API_QUERIES}" ]; then
    #echo -e "${BRed}Nothing to proxy. Abort${Color_Off}"
    #exit 255
#fi

declare -A SERVICE_WATCH_PIDS
declare -A API_MANAGEMENT_PIDS
#./serialize_unmet_deps_into_schema_files.py "${PROXYING_API_QUERIES}" "to_proxy"
#for service in to_proxy/*
#do
#    echo -e "Generate proxy for ${BBlue}${service}${Color_Off}:"
#    ./build_proxy_services.py "${service}" -os "${service}/generated" -oe "${service}/exec_generated"
#    ${OPT_DIR}/build_api_pseudo_fs.py "${service}" ${SHARED_API_DIR}
#    launch_fs_api_services SERVICE_WATCH_PIDS "${service}/generated"
#
#    ${OPT_DIR}/api_management.py "${service}" ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} &
#    API_MANAGEMENT_PIDS[${service}]=$!
#done


termination_handler(){
    gracefull_shutdown_bunch SERVICE_WATCH_PIDS API_MANAGEMENT_PIDS
}
echo "Setup signal handlers"
trap 'termination_handler' SIGHUP SIGQUIT SIGABRT SIGKILL SIGALRM SIGTERM EXIT

shopt -s extglob
RETURN_STATUS=0
TIMEOUT_ON_FAILURE_SEC=1
WAIT_FOR_HEARTBEAT_PIPE_IN_CREATION_SEC=5
WAIT_FOR_HEARTBEAT_PIPE_OUT_CREATION_SEC=3
UPSTREAM_SERVICE_HEARTBEAT_SEC=15

API_UPDATE_EVENT_TIMEOUT_LIMIT=15
API_UPDATE_EVENT_TIMEOUT_COUNTER=0
# Loop until any unrecoverable error would occur
HAS_GOT_API_UPDATE_EVENT=0

rm -rf to_proxy
rm -rf to_proxy_new
if [ ! -d "to_proxy" ]; then
    # make empty directory to fill it in by newly detected services
    mkdir to_proxy
fi
while [ ${API_UPDATE_EVENT_TIMEOUT_COUNTER} != ${API_UPDATE_EVENT_TIMEOUT_LIMIT} ]; do

    # wait until upstream service become alive...
    wait_for_pipe_exist ${pipe_in} WAIT_RESULT ${WAIT_FOR_HEARTBEAT_PIPE_IN_CREATION_SEC}
    if [ ${WAIT_RESULT} -eq 255 ] ; then
        echo -e "${BPurple}PIPE IN: ${pipe_in} doesn't exist${Color_Off}, trying again in attempt: ${BPurple}(${API_UPDATE_EVENT_TIMEOUT_COUNTER}/${API_UPDATE_EVENT_TIMEOUT_LIMIT})${Color_Off}"
        sleep ${TIMEOUT_ON_FAILURE_SEC} &
        wait $!
        let API_UPDATE_EVENT_TIMEOUT_COUNTER=${API_UPDATE_EVENT_TIMEOUT_COUNTER}+1
        continue
    fi

    # upstream service may get inoperable abruptly, to prevent stucking on a dead-pipe, let's not block ourselves on it,
    # so that a watchdog introduced
    (echo "SESSION_ID=${SESSION_ID} --service=${DOWNSTREAM_SERVICE}"> ${pipe_in}) &
    PID_TO_UNBLOCK=$!
    sleep 2
    kill -s 0 ${PID_TO_UNBLOCK} > /dev/null 2>&1
    PID_TO_UNBLOCK_RESULT=$?
    if [ $PID_TO_UNBLOCK_RESULT == 0 ]; then
        # query has stucked: probably due to upstream service outage. Unblock query
        timeout 2 cat ${pipe_in} > /dev/null 2>&1
        if [ $? == 124 ] ; then echo "`date +%H:%M:%S:%3N`	`hostname`	RESET:	${pipe_in}"; fi
        echo -e "${BReg}Heartbeat query: ${pipe_in} has stuck on${Color_Off} probably due to ${BRed}${UPSTREAM_SERVICE}${Color_Off} outage, trying again in attempt: ${BRed}(${API_UPDATE_EVENT_TIMEOUT_COUNTER}/${API_UPDATE_EVENT_TIMEOUT_LIMIT})${Color_Off}"
        let API_UPDATE_EVENT_TIMEOUT_COUNTER=${API_UPDATE_EVENT_TIMEOUT_COUNTER}+1
        continue
    fi

    # wait until upstream service create OUT pipe to read on
    wait_for_pipe_exist ${pipe_out} WAIT_RESULT ${WAIT_FOR_HEARTBEAT_PIPE_OUT_CREATION_SEC}
    if [ ${WAIT_RESULT} -eq 255 ] ; then
        echo -e "${BPurple}PIPE OUT: ${pipe_out} doesn't exist${Color_Off}, trying again in attempt: ${BPurple}(${API_UPDATE_EVENT_TIMEOUT_COUNTER}/${API_UPDATE_EVENT_TIMEOUT_LIMIT})${Color_Off}"
        sleep ${TIMEOUT_ON_FAILURE_SEC} &
        wait $!
        let API_UPDATE_EVENT_TIMEOUT_COUNTER=${API_UPDATE_EVENT_TIMEOUT_COUNTER}+1
        continue
    fi


    # upstream service may get inoperable abruptly, to prevent stucking on a dead-pipe, let's not block ourselves on it,
    # so that a watchdog introduced.
    file_pipe_out_result_name=cat_pipe_out_result_file
    rm -f ${file_pipe_out_result_name}*
    file_pipe_out_result_name="${file_pipe_out_result_name}_`date +%s`"
    (cat ${pipe_out} > ${file_pipe_out_result_name}) &
    PID_TO_UNBLOCK=$!
    sleep 2
    kill -s 0 ${PID_TO_UNBLOCK} > /dev/null 2>&1
    PID_TO_UNBLOCK_RESULT=$?
    if [ $PID_TO_UNBLOCK_RESULT == 0 ]; then
        # query has stucked: probably due to upstream service outage. Unblock query
        timeout 2 echo > ${pipe_out} > /dev/null 2>&1
        if [ $? == 124 ] ; then echo "`date +%H:%M:%S:%3N`	`hostname`	RESET:	${pipe_out}"; fi
        echo -e "${BRed}Heartbeat query: ${pipe_out} has stuck on{Color_Off} probably due to ${BRed}${UPSTREAM_SERVICE}${Color_Off} outage, trying again in attempt: ${BRed}(${API_UPDATE_EVENT_TIMEOUT_COUNTER}/${API_UPDATE_EVENT_TIMEOUT_LIMIT})${Color_Off}"
        let API_UPDATE_EVENT_TIMEOUT_COUNTER=${API_UPDATE_EVENT_TIMEOUT_COUNTER}+1
        continue
    fi

    PROXYING_API_QUERIES=`cat ${file_pipe_out_result_name}`
    if [ -z "${PROXYING_API_QUERIES}" ]; then
        sleep ${UPSTREAM_SERVICE_HEARTBEAT_SEC} &
        wait $!
        continue
    fi

    echo -e "${Green}Upstream service: ${BGreen}${UPSTREAM_SERVICE}${Green} got dependencies changed: ${BGreen}${PROXYING_API_QUERIES}${Color_Off}"
    rm -rf to_proxy_new
    ./serialize_unmet_deps_into_schema_files.py "${PROXYING_API_QUERIES}" "to_proxy_new"

    # compare files
    declare -A SERVICE_TO_STOP
    declare -A API_MANAGEMENT_PIDS_TO_STOP
    declare -A SERVICE_TO_RUN
    while IFS= read -r CMD;
    do
        if [ ${CMD:0:3} == "---" ] || [ ${CMD:0:3} == "+++" ]; then
            continue
        fi

        # Compare content of an existing directory against content of the new `to_proxy_new` directory
        # Services to stop starting with the prefix "-", which means they are not required anymore
        # and service to add are starting with the prefix "+"
        if [ ${CMD:0:1} == "-" ] ;
        then
            OLD_SERVICE_NAME=`echo ${CMD:1:32768} | xargs`
            OLD_SERVICE_FILE_PATH="to_proxy/${OLD_SERVICE_NAME}"
            if [ ! -z ${SERVICE_WATCH_PIDS[${OLD_SERVICE_FILE_PATH}]} ] ; then
                SERVICE_TO_STOP[${OLD_SERVICE_FILE_PATH}]=${SERVICE_WATCH_PIDS[${OLD_SERVICE_FILE_PATH}]}
                rm ${OLD_SERVICE_FILE_PATH}
            fi
            unset SERVICE_WATCH_PIDS[${OLD_SERVICE_FILE_PATH}]

            if [ ! -z ${API_MANAGEMENT_PIDS[${OLD_SERVICE_FILE_PATH}]} ] ; then
                API_MANAGEMENT_PIDS_TO_STOP[${OLD_SERVICE_FILE_PATH}] = ${OLD_SERVICE_FILE_PATH[${OLD_SERVICE_FILE_PATH}]}
            fi
            unset API_MANAGEMENT_PIDS[${OLD_SERVICE_FILE_PATH}]

        elif [ ${CMD:0:1} == "+" ] ;
        then
            NEW_SERVICE_NAME=`echo ${CMD:1:32768} | xargs`
            NEW_SERVICE_FILE_PATH="to_proxy/${NEW_SERVICE_NAME}"
            cp -r "to_proxy_new/${NEW_SERVICE_NAME}" ${NEW_SERVICE_FILE_PATH}

            SERVICE_TO_RUN[${NEW_SERVICE_FILE_PATH}]=""

        fi
    done <<< `diff -s <(ls to_proxy) <(ls to_proxy_new)`

    echo -e "${BBlue}Stop old services${Color_Off}, which are not required by ${UPSTREAM_SERVICE} anymore:"
    gracefull_shutdown_bunch SERVICE_TO_STOP API_MANAGEMENT_PIDS_TO_STOP

    echo -e "${BBlue}Launch new services${Color_Off}, which ${UPSTREAM_SERVICE} has become depend on: ${!SERVICE_TO_RUN[@]}"
    for service in ${!SERVICE_TO_RUN[@]}
    do
        echo -e "Generate proxy for ${BBlue}${service}${Color_Off}:"
        ./build_proxy_services.py "${service}" -os "${service}/generated" -oe "${service}/exec_generated"
        ${OPT_DIR}/build_api_pseudo_fs.py "${service}" ${SHARED_API_DIR}

        # for each 'service' launch all its query-servers
        launch_fs_api_services SERVICE_WATCH_PIDS "${service}/generated"

        ${OPT_DIR}/api_management.py "${service}" ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} &
        API_MANAGEMENT_PIDS[${service}]=$!
    done
done

termination_handler
echo "Exit with code: ${RETURN_STATUS}"
exit ${RETURN_STATUS}
