#!/bin/bash

source ${OPT_DIR}/shell_utils/color_codes.sh

gracefull_shutdown() {
    local -n SERVICE_WATCH_PIDS_TO_STOP=${1}
    API_MANAGEMENT_PID=${2}

    echo -e "`date +%H:%M:%S:%3N`    ${BRed}***Shutdown servers***${Color_Off}"
    ps -ef
    for server_script_path in "${!SERVICE_WATCH_PIDS_TO_STOP[@]}"
    do
        echo "${BRed}Kill ${server_script_path}${Color_Off} by PID: {${SERVICE_WATCH_PIDS_TO_STOP[$server_script_path]}}"
        pkill -KILL -e -P ${SERVICE_WATCH_PIDS_TO_STOP[$server_script_path]}
        kill -9 ${SERVICE_WATCH_PIDS_TO_STOP[$server_script_path]}
        ps -ef
    done
    echo -e "`date +%H:%M:%S:%3N`    ${BRed}***Clear pipes****${Color_Off}"
    kill -s SIGTERM ${API_MANAGEMENT_PID}
    while true
    do
        kill -s 0 ${API_MANAGEMENT_PID}
        RESULT=$?
        if [ $RESULT == 0 ]; then
            continue
        fi
        break
    done
    echo -e "`date +%H:%M:%S:%3N`    ${BRed}***Done****${Color_Off}"
}

launch_fs_api_services() {
    local -n service_pids_arr=${1}
    SERVICES_SCRIPTS_PATH=${2}
    echo -e "${BBlue}Run API services from ${SERVICES_SCRIPTS_PATH}:${Color_Off}"
    for s in ${SERVICES_SCRIPTS_PATH}/*.sh; do
        /bin/bash ${s} &
        service_pids_arr[${s}]=$!
        echo "${s} has been started, PID ${service_pids_arr[${s}]}"
    done
}

wait_for_unavailable_services() {
    SHARED_API_MOUNT_DIR=${1}
    OWN_SERVICE_NAME=${2}
    let wait_dependencies_counter=0
    wait_dependencies_counter_limit=${4}
    if [ -z ${wait_dependencies_counter_limit} ]; then
        echo "as wait_dependencies_counter_limit is not set use default value 30"
        wait_dependencies_counter_limit=30
    fi
    let wait_dependencies_counter_limit=${wait_dependencies_counter_limit}

    let wait_dependencies_sec=1
    ANY_SERVICE_UNAVAILABLE=1
    SESSION_ID="`hostname`_watchdog"
    pipe_in="${SHARED_API_MOUNT_DIR}/${OWN_SERVICE_NAME}/unmet_dependencies/GET/exec"
    pipe_out="${SHARED_API_MOUNT_DIR}/${OWN_SERVICE_NAME}/unmet_dependencies/GET/result.json_${SESSION_ID}"

    while [ ! -p ${pipe_in} ]; do sleep 0.1; done
    while true :
    do
        ANY_SERVICE_UNAVAILABLE=
        echo "SESSION_ID=${SESSION_ID}"> ${pipe_in}
        while [ ! -p ${pipe_out} ]; do sleep 0.1; done
        MISSING_API_QUERIES=`cat ${pipe_out}`

        if [ ! -z "${MISSING_API_QUERIES}" ]; then
            echo -e "${Blue}One or more services are unavailable using this API:${Color_Off}"
            echo -e "${Blue}${MISSING_API_QUERIES}${Color_Off}"
            let ANY_SERVICE_UNAVAILABLE=${ANY_SERVICE_UNAVAILABLE}+1
        fi
        if [ -z ${ANY_SERVICE_UNAVAILABLE} ]; then
            break
        fi
        if [ ${wait_dependencies_counter} == ${wait_dependencies_counter_limit} ]; then
            eval ${3}=$ANY_SERVICE_UNAVAILABLE
            break
        fi
        let wait_dependencies_counter=$wait_dependencies_counter+1
        echo -e "${Red}WARNING: One or more services are offline. Another attempt: ${wait_dependencies_counter}/${wait_dependencies_counter_limit} - will be made in ${wait_dependencies_sec} seconds.${Color_Off}"
        sleep ${wait_dependencies_sec} &
        wait $!
    done
}

get_unavailable_services() {
    API_DEPS_PATH=${1}
    let wait_dependencies_counter=0
    let wait_dependencies_counter_limit=30
    let wait_dependencies_sec=1
    ANY_SERVICE_UNAVAILABLE=1
    while :
    do
        ANY_SERVICE_UNAVAILABLE=
        for deps_service in ${API_DEPS_PATH}/*; do
            if [ -d ${deps_service} ]; then
                MISSING_API_QUERIES=`${3} ${deps_service}`
                if [ ! -z "${MISSING_API_QUERIES}" ]; then
                    echo "The service \"${deps_service}\" is unavailable using this API:"
                    echo "${MISSING_API_QUERIES}"
                    let ANY_SERVICE_UNAVAILABLE=${ANY_SERVICE_UNAVAILABLE}+1
                fi
            fi
        done
        if [ -z ${ANY_SERVICE_UNAVAILABLE} ]; then
            break
        fi
        if [ ${wait_dependencies_counter} == ${wait_dependencies_counter_limit} ]; then
            eval ${2}=$ANY_SERVICE_UNAVAILABLE
            break
        fi
        let wait_dependencies_counter=$wait_dependencies_counter+1
        echo "WARNING: One or more services are offline. Another attempt: ${wait_dependencies_counter}/${wait_dependencies_counter_limit} - will be made in ${wait_dependencies_sec} seconds."
        sleep ${wait_dependencies_sec} &
        wait $!
    done

}
