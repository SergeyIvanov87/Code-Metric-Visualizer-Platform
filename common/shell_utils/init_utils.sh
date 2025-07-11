#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

source ${SCRIPT_DIR}/color_codes.sh

gracefull_shutdown() {
    local -n SERVICE_WATCH_PIDS_TO_STOP=${1}
    local API_MANAGEMENT_PID=${2}

    echo -e "`date +%H:%M:%S:%3N`    ${BRed}***Shutdown servers***${Color_Off}"
    ps -ef
    for server_script_path in "${!SERVICE_WATCH_PIDS_TO_STOP[@]}"
    do
        echo -e "${BRed}Kill ${server_script_path}${Color_Off} by PID: ${Red}${SERVICE_WATCH_PIDS_TO_STOP[$server_script_path]}${Color_Off}"
        pkill -KILL -e -P ${SERVICE_WATCH_PIDS_TO_STOP[$server_script_path]}
        kill -9 ${SERVICE_WATCH_PIDS_TO_STOP[$server_script_path]}
        ps -ef
    done
    echo -e "`date +%H:%M:%S:%3N`    ${BRed}***Clear pipes, killing PID: ${Red}${API_MANAGEMENT_PID}${BRed}****${Color_Off}"
    kill -s SIGTERM ${API_MANAGEMENT_PID}
    while true
    do
        kill -s 0 ${API_MANAGEMENT_PID}
        RESULT=$?
        if [ $RESULT == 0 ]; then
            echo -e "`date +%H:%M:%S:%3N`    ${Blue}***API_MANAGEMENT_PID: ${API_MANAGEMENT_PID} still exist****${Color_Off}"
            sleep 1
            continue
        fi
        break
    done
    echo -e "`date +%H:%M:%S:%3N`    ${BRed}***Done****${Color_Off}"
}

gracefull_shutdown_bunch() {
    local -n service_watch_pids_to_stop=${1}
    local -n api_management_pids=${2}
    if [ ${#service_watch_pids_to_stop[@]} -ne 0 ] ; then
        echo -e "`date +%H:%M:%S:%3N`    ${BRed}***Shutdown servers***${Color_Off}"
        ps -ef
        for server_script_path in "${!service_watch_pids_to_stop[@]}"
        do
            echo -e "${BRed}Kill ${server_script_path}${Color_Off} by PID: ${Red}${service_watch_pids_to_stop[$server_script_path]}${Color_Off}"
            pkill -KILL -e -P ${service_watch_pids_to_stop[$server_script_path]}
            kill -9 ${service_watch_pids_to_stop[$server_script_path]}
            ps -ef
        done
        echo -e "`date +%H:%M:%S:%3N`    ${BRed}***Shutdown servers --- DONE***${Color_Off}"
    fi
    if [ ${#api_management_pids[@]} -ne 0 ]; then
        for service_name in ${!api_management_pids[@]}
        do
            service_pid=${api_management_pids[$service_name]}
            echo -e "`date +%H:%M:%S:%3N`    ${BRed}***Clear pipes, killing PID: ${Red}${service_pid}${BRed} of ${Red}${service_name}${BRed}****${Color_Off}"
            kill -s SIGTERM ${service_pid}
            while true
            do
                kill -s 0 ${service_pid}
                RESULT=$?
                if [ $RESULT == 0 ]; then
                    echo -e "`date +%H:%M:%S:%3N`    ${Blue}***service_pid: ${service_pid} still exist****${Color_Off}"
                    sleep 1
                    continue
                fi
                break
            done
        done
        echo -e "`date +%H:%M:%S:%3N`    ${BRed}***Clear pipes --- Done****${Color_Off}"
    fi
}

wait_for_pipe_exist() {
    local pipe=${1}
    local pipe_wait_timeout_sec=0.1
    local pipe_wait_timeout_limit=${3}
    local pipe_wait_timeout_counter=0
    local ret_code=0
    while [ ! -p ${pipe} ];
    do
        sleep ${pipe_wait_timeout_sec}
        echo "waiting for pipe: ${pipe}, attempt: [${pipe_wait_timeout_counter}/${pipe_wait_timeout_limit}]"
        let pipe_wait_timeout_counter=${pipe_wait_timeout_counter}+1
        if [ ${pipe_wait_timeout_counter} == ${pipe_wait_timeout_limit} ]; then
            ret_code=255
            break
        fi
    done
    eval ${2}=${ret_code}

}

launch_fs_api_services() {
    local -n service_pids_arr=${1}
    local SERVICES_SCRIPTS_PATH=${2}
    echo -e "${BBlue}Run API services from ${SERVICES_SCRIPTS_PATH}:${Color_Off}"
    for s in ${SERVICES_SCRIPTS_PATH}/*.sh; do
        /bin/bash ${s} &
        service_pids_arr[${s}]=$!
        echo "${s} has been started, PID ${service_pids_arr[${s}]}"
    done
}

launch_command_api_services() {
    local -n in_out_service_pids_arr=${1}
    local command_api_schema_dir=${2}
    local work_dir=${3}
    local shared_api_dir_for_meta_fs_mount=${4}
    local full_service_name=${5}

    ${OPT_DIR}/canonize_internal_api.py ${command_api_schema_dir} ${full_service_name}
    ${OPT_DIR}/build_common_api_services.py ${command_api_schema_dir} -os ${work_dir}/aux_services -oe ${work_dir}
    ${OPT_DIR}/build_api_pseudo_fs.py ${command_api_schema_dir} ${shared_api_dir_for_meta_fs_mount}

    launch_fs_api_services in_out_service_pids_arr "${work_dir}/aux_services"
}

launch_inner_api_services() {
    local -n in_out_inner_service_pids_arr=${1}
    local inner_api_schema_dir=${2}
    local work_dir=${3}
    local shared_api_dir_for_meta_fs_mount=${4}
    local out_readme_file_path_=${5}

    ${OPT_DIR}/build_api_executors.py ${inner_api_schema_dir} ${work_dir} -o ${work_dir}
    ${OPT_DIR}/build_api_services.py ${inner_api_schema_dir} ${work_dir} -o ${work_dir}/services
    ${OPT_DIR}/build_api_pseudo_fs.py ${inner_api_schema_dir} ${shared_api_dir_for_meta_fs_mount}
    ${OPT_DIR}/make_api_readme.py ${inner_api_schema_dir} > ${out_readme_file_path_}

    launch_fs_api_services in_out_inner_service_pids_arr "${work_dir}/services"
}

wait_for_unavailable_services() {
    local SHARED_API_MOUNT_DIR=${1}
    local OWN_SERVICE_NAME=${2}
    local let wait_dependencies_counter=0
    local wait_dependencies_counter_limit=${4}
    if [ -z ${wait_dependencies_counter_limit} ]; then
        echo "as wait_dependencies_counter_limit is not set use default value 30"
        wait_dependencies_counter_limit=30
    fi
    let wait_dependencies_counter_limit=${wait_dependencies_counter_limit}

    local let wait_dependencies_sec=1
    local ANY_SERVICE_UNAVAILABLE=1
    local SESSION_ID="`hostname`_watchdog"
    local pipe_in="${SHARED_API_MOUNT_DIR}/${OWN_SERVICE_NAME}/unmet_dependencies/GET/exec"
    local pipe_out="${SHARED_API_MOUNT_DIR}/${OWN_SERVICE_NAME}/unmet_dependencies/GET/result.json_${SESSION_ID}"

    while [ ! -p ${pipe_in} ]; do sleep 0.1; done
    while true :
    do
        ANY_SERVICE_UNAVAILABLE=
        echo "SESSION_ID=${SESSION_ID}"> ${pipe_in}
        while [ ! -p ${pipe_out} ]; do sleep 0.1; done
        local MISSING_API_QUERIES=`cat ${pipe_out}`

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
    local API_DEPS_PATH=${1}
    local let wait_dependencies_counter=0
    local let wait_dependencies_counter_limit=30
    local let wait_dependencies_sec=1
    local ANY_SERVICE_UNAVAILABLE=1
    while :
    do
        ANY_SERVICE_UNAVAILABLE=
        for deps_service in ${API_DEPS_PATH}/*; do
            if [ -d ${deps_service} ]; then
                local MISSING_API_QUERIES=`${3} ${deps_service}`
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
