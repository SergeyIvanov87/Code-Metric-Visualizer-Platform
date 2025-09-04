#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

source ${SCRIPT_DIR}/color_codes.sh

gracefull_shutdown() {
    echo -e "${BBlue}Starting gracefull shutdown routine${Color_Off}"
    local -n service_watch_pids_to_stop=${1}
    local api_management_pid=${2}

    echo -e "`date +%H:%M:%S:%3N`    ${BRed}***Shutdown servers***${Color_Off}"
    ps -ef
    for server_script_path in "${!service_watch_pids_to_stop[@]}"
    do
        echo -e "${BRed}Kill ${server_script_path}${Color_Off} by PID: ${Red}${service_watch_pids_to_stop[$server_script_path]}${Color_Off}"
        pkill -KILL -e -P ${service_watch_pids_to_stop[$server_script_path]}
        kill -9 ${service_watch_pids_to_stop[$server_script_path]}
        ps -ef
    done
    echo -e "`date +%H:%M:%S:%3N`    ${BRed}***Clear pipes, killing PID: ${Red}${API_MANAGEMENT_PID}${BRed}****${Color_Off}"
    kill -s SIGTERM ${api_management_pid}
    while true
    do
        kill -s 0 ${api_management_pid} > /dev/null 2>&1
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
        for service_name in "${!api_management_pids[@]}"
        do
            service_pid=${api_management_pids[${service_name}]}
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


wait_until_pipe_appear() {
    local pipe=${1}
    local func_arg_read_message=""

    local pipe_wait_timeout_limit=${2}
    if [ -z "${pipe_wait_timeout_limit}" ]; then
        pipe_wait_timeout_limit=5
        func_arg_read_message="As \"wait_until_pipe_appear\" got no argument \"pipe_wait_timeout_limit\" value set, use default: ${pipe_wait_timeout_limit}"
    fi

    local pipe_wait_timeout_sec=${3}
    if [ -z "${pipe_wait_timeout_sec}" ]; then
        pipe_wait_timeout_sec=0.1
        func_arg_read_message="${func_arg_read_message}. As \"wait_until_pipe_appear\" got no argument \"pipe_wait_timeout_sec\" value set, use default: ${pipe_wait_timeout_sec}"
    fi

    if [ ! -z "${func_arg_read_message}" ]; then echo "${func_arg_read_message}"; fi

    local pipe_wait_timeout_counter=0
    while [ ! -p ${pipe} ];
    do
        sleep ${pipe_wait_timeout_sec}
        let pipe_wait_timeout_counter=${pipe_wait_timeout_counter}+1
        if [ ${pipe_wait_timeout_counter} == ${pipe_wait_timeout_limit} ]; then
            echo "The pipe: ${pipe}, didn't set up in attempts: [${pipe_wait_timeout_counter}/${pipe_wait_timeout_limit}]"
            return 255
        fi
    done
    return 0
}

send_ka_watchdog_query() {
    local pipe_in=${1}
    local session_id=${2}
    local downstream_service=${3}
    local send_ka_query_timeout=${4}
     if [ -z "${send_ka_query_timeout}" ]; then
        send_ka_query_timeout=15
        echo "As \"send_ka_watchdog_query\" got no argument \"send_ka_query_timeout\" value set, use default: ${send_ka_query_timeout}"
    fi

    wait_until_pipe_appear ${pipe_in} 3 1
    if [ $? -eq 255 ] ; then
        echo "Cannot send KA watchdog query as no queries through IN pipe have been made: ${pipe_in} has been failed. Elapsed cycles: 3"
        return 255
    fi

    echo -e "Send watchdog query ${Cyan}${session_id}${Color_Off} to the pipe: ${pipe_in}, timeout: ${send_ka_query_timeout}"
    local deps_query_timeout_protection_sec=${send_ka_query_timeout}
    let deps_query_timeout_protection_sec=${deps_query_timeout_protection_sec}+3
    timeout ${deps_query_timeout_protection_sec} /bin/bash -c "echo \"SESSION_ID=${session_id} --service=${downstream_service} --timeout=${send_ka_query_timeout}\"> ${pipe_in}"
    if [ $? == 124 ] ; then
        echo "`date +%H:%M:%S:%3N`	`hostname`	RESET:	${pipe_in}";
        return 255
    fi
    return 0
}

receive_ka_watchdog_query() {
    local pipe_out=${1}
    local result_timeout_sec=${2}
    if [ -z "${result_timeout_sec}" ]; then
        result_timeout_sec=5
        echo "As \"receive_ka_watchdog_query\" got no argument \"result_timeout_sec\" value set, use default: ${result_timeout_sec}"
    fi

    local start_time
    local end_time
    start_time=$(date +%s)
    wait_until_pipe_appear ${pipe_out} ${result_timeout_sec} 1
    if [ $? -eq 255 ] ; then
        echo "Cannot send KA watchdog query as waiting IN pipe readiness: ${pipe_out} has been failed. Elapsed cycles: ${result_timeout_sec}"
        return 255
    fi
    end_time=$(date +%s)
    let result_timeout_sec=${result_timeout_sec}+${start_time}-${end_time}

    echo -e "Try to receive watchdog query on pipe: ${Cyan}${pipe_out}${Color_Off}, timeout: ${result_timeout_sec}"
    local watchdog_query_response_missing_services
    watchdog_query_response_missing_services=$(timeout ${result_timeout_sec} /bin/bash -c "cat ${pipe_out}")
    if [ $? == 124 ] ; then
        # query has stucked: probably due to upstream service outage. Unblock query
        echo "`date +%H:%M:%S:%3N`	`hostname`	RESET:	${pipe_out}";
        return 255
    fi
    eval ${3}='${watchdog_query_response_missing_services}'
    return 0
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

doas_launch_command_api_services() {
    local -n in_out_service_pids_arr=${1}
    local command_api_schema_dir=${2}
    local work_dir=${3}
    local shared_api_dir_for_meta_fs_mount=${4}
    local full_service_name=${5}

    ${OPT_DIR}/canonize_internal_api.py ${command_api_schema_dir} ${full_service_name}
    ${OPT_DIR}/build_common_api_services.py ${command_api_schema_dir} -os ${work_dir}/aux_services -oe ${work_dir}
    doas -u root env PYTHONPATH=${PYTHONPATH} SHARED_API_DIR=${shared_api_dir_for_meta_fs_mount} MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME} ${OPT_DIR}/build_api_pseudo_fs.py ${command_api_schema_dir} ${shared_api_dir_for_meta_fs_mount}
    doas -u root chown -R $USER:$GROUPNAME ${shared_api_dir_for_meta_fs_mount}/${full_service_name}
    ls -laR ${shared_api_dir_for_meta_fs_mount}/${full_service_name}
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
    # Do not generate readme unles the server completely started
    #${OPT_DIR}/make_api_readme.py ${inner_api_schema_dir} > ${out_readme_file_path_}
    #chmod g+rw ${out_readme_file_path_}
    #${OPT_DIR}/make_api_readme.py ${inner_api_schema_dir}  | ( umask 0033; cat >> ${out_readme_file_path_} )

    launch_fs_api_services in_out_inner_service_pids_arr "${work_dir}/services"
}

doas_launch_inner_api_services() {
    local -n in_out_inner_service_pids_arr=${1}
    local inner_api_schema_dir=${2}
    local work_dir=${3}
    local shared_api_dir_for_meta_fs_mount=${4}
    local out_readme_file_path_=${5}
    local full_service_name=${6}

    ${OPT_DIR}/build_api_executors.py ${inner_api_schema_dir} ${work_dir} -o ${work_dir}
    ${OPT_DIR}/build_api_services.py ${inner_api_schema_dir} ${work_dir} -o ${work_dir}/services
    doas -u root env PYTHONPATH=${PYTHONPATH} SHARED_API_DIR=${shared_api_dir_for_meta_fs_mount} MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME} ${OPT_DIR}/build_api_pseudo_fs.py ${inner_api_schema_dir} ${shared_api_dir_for_meta_fs_mount}
    doas -u root chown -R $USER:$GROUPNAME ${shared_api_dir_for_meta_fs_mount}/${full_service_name}
    ls -laR ${shared_api_dir_for_meta_fs_mount}/${full_service_name}

    # Do not generate readme unles the server completely started
    #${OPT_DIR}/make_api_readme.py ${inner_api_schema_dir} > ${out_readme_file_path_}
    #chmod g+rw ${out_readme_file_path_}
    #${OPT_DIR}/make_api_readme.py ${inner_api_schema_dir}  | ( umask 0033; cat >> ${out_readme_file_path_} )

    launch_fs_api_services in_out_inner_service_pids_arr "${work_dir}/services"
}


wait_for_unavailable_services() {
    local shared_api_mount_dir=${1}
    local own_service_name=${2}

    local func_arg_read_message=""
    local wait_dependencies_counter_limit=${3}
    if [ -z "${wait_dependencies_counter_limit}" ]; then
        wait_dependencies_counter_limit=30
        func_arg_read_message="As \"wait_dependencies_counter_limit\" is not set, use default value: ${wait_dependencies_counter_limit}."
    fi

    local send_ka_query_timeout=${4}
    if [ -z "${send_ka_query_timeout}" ]; then
        send_ka_query_timeout=15
        func_arg_read_message="${func_arg_read_message} As \"send_ka_query_timeout\" is not set, use default value: ${send_ka_query_timeout}."
    fi

    local receive_ka_query_timeout=${5}
    if [ -z "${receive_ka_query_timeout}" ]; then
        receive_ka_query_timeout=5
        func_arg_read_message="${func_arg_read_message} As \"receive_ka_query_timeout\" is not set, use default value: ${receive_ka_query_timeout}"
    fi

    if [ ! -z "${func_arg_read_message}" ]; then echo "${func_arg_read_message}"; fi

    let wait_dependencies_counter_limit=${wait_dependencies_counter_limit}
    let send_ka_query_timeout=${send_ka_query_timeout}
    let receive_ka_query_timeout=${receive_ka_query_timeout}
    local wait_dependencies_counter
    let wait_dependencies_counter=0

    local wait_dependencies_sec
    let wait_dependencies_sec=1
    local session_id="`hostname`_watchdog"
    local pipe_in="${shared_api_mount_dir}/${own_service_name}/unmet_dependencies/GET/exec"
    local pipe_out="${shared_api_mount_dir}/${own_service_name}/unmet_dependencies/GET/result.json_${session_id}"
    ls -la "${shared_api_mount_dir}/${own_service_name}/unmet_dependencies/GET/"
    rm -f ${pipe_out}

    wait_until_pipe_appear ${pipe_in} -1 1
    if [ $? -eq 255 ] ; then
        echo -e "${BRed}Waiting for IN pipe appearance: ${pipe_in} failed. Elapsed cycles: -1${Color_Off}"
        return 255
    fi

    local pipe_couter=1
    while true :
    do
        send_ka_watchdog_query ${pipe_in} ${session_id} ".*" ${send_ka_query_timeout}
        if [ $? == 255 ]; then
            let wait_dependencies_counter=$wait_dependencies_counter+1
            echo -e "Wait for another attempt: ${BCyan}${wait_dependencies_counter}/${wait_dependencies_counter_limit}${Color_Off}"
            if [ ${wait_dependencies_counter} == ${wait_dependencies_counter_limit} ]; then
                echo -e "${BRed}Couldn't send/get KA probe result, all attempts: ${wait_dependencies_counter_limit} - failed${Color_Off}"
                return 254
            fi
            continue
        fi


        pipe_couter=1
        while [ ! -p ${pipe_out} ];
        do
            sleep 0.1;
            if [ $((pipe_couter / 3)) == 0  ]; then
                echo "Waiting for OUT pipe appearance: ${pipe_out}... Elapsed cycles: ${pipe_couter}"
            fi
            let pipe_couter=$pipe_couter+1
        done

        # As we use ephemeral pipe, which have to be created after query sent,
        # it is possible to face the situation when the new pipe creation may be delayed
        # but some inactive dead-pipe having the same name still exist.
        # Reading this dead-pipe may be a reason of a deadlock
        # So let's read this pipe in async mode
        local missing_api_queries
        missing_api_queries=
        receive_ka_watchdog_query ${pipe_out} ${receive_ka_query_timeout} missing_api_queries
        if [ $? == 255 ]; then
            echo -e "Wait for another attempt: ${BCyan}${wait_dependencies_counter}/${wait_dependencies_counter_limit}${Color_Off}"
            let wait_dependencies_counter=$wait_dependencies_counter+1
            if [ ${wait_dependencies_counter} == ${wait_dependencies_counter_limit} ]; then
                echo -e "${BRed}Couldn't get KA probe result, all attempts: ${wait_dependencies_counter_limit} - failed${Color_Off}"
                return 252
            fi
            continue
        fi

        if [ -z "${missing_api_queries}" ]; then
            return 0
        fi

        if [ ${wait_dependencies_counter} == ${wait_dependencies_counter_limit} ];
        then
            echo -e "${Blue}One or more services are unavailable using this API:${Color_Off}"
            echo -e "${Blue}${missing_api_queries}${Color_Off}"
            return 250
        fi
        let wait_dependencies_counter=$wait_dependencies_counter+1
        echo -e "${Red}WARNING: One or more services are offline: ${missing_api_queries}. Another attempt: ${wait_dependencies_counter}/${wait_dependencies_counter_limit} - will be made in ${wait_dependencies_sec} seconds.${Color_Off}"
        sleep ${wait_dependencies_sec} &
        wait $!
    done
    return 0
}

get_unavailable_services() {
    local API_DEPS_PATH=${1}
    local wait_dependencies_counter
    let wait_dependencies_counter=0
    local wait_dependencies_counter_limit
    let wait_dependencies_counter_limit=30
    local wait_dependencies_sec
    let wait_dependencies_sec=1
    local ANY_SERVICE_UNAVAILABLE=1
    while :
    do
        ANY_SERVICE_UNAVAILABLE=
        for deps_service in ${API_DEPS_PATH}/*; do
            if [ -d ${deps_service} ]; then
                local missing_api_queries=`${3} ${deps_service}`
                if [ ! -z "${missing_api_queries}" ]; then
                    echo "The service \"${deps_service}\" is unavailable using this API:"
                    echo "${missing_api_queries}"
                    let ANY_SERVICE_UNAVAILABLE=${ANY_SERVICE_UNAVAILABLE}+1
                fi
            fi
        done
        if [ -z "${ANY_SERVICE_UNAVAILABLE}" ]; then
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
