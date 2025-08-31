#!/bin/bash

export WORK_DIR=${1}
export OPT_DIR=${2}
export PYTHONPATH="${2}:${2}/modules"
export SHARED_API_DIR=${3}
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

# start & activate syslogd
doas -u root rc-status
doas -u root touch /run/openrc/softlevel
doas -u root rc-service syslog start
doas -u root rc-service syslog status

# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport OPT_DIR=${OPT_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh

source ${OPT_DIR}/shell_utils/init_utils.sh

echo -e "${Blue}Proxy UPSTREAM_SERVICE: ${BBlue}${UPSTREAM_SERVICE}${Blue}, DOWNSTREAM_SERVICE: ${BBlue}${DOWNSTREAM_SERVICE}${Blue}, DOWNSTREAM_SERVICE_NETWORK_ADDR: ${BBlue}${DOWNSTREAM_SERVICE_NETWORK_ADDR}${Color_Off}"
if [ -z "${UPSTREAM_SERVICE}" ]; then
    echo -e "${BRed}ERROR:${Color_Off}The environment variable ${BRed}UPSTREAM_SERVICE${Color_Off} is not configured. Cannot start without proxying anything"
    exit 255
fi

if [ -z "${DOWNSTREAM_SERVICE}" ]; then
    echo -e "${BRed}ERROR:${Color_Off}The environment variable ${BRed}DOWNSTREAM_SERVICE${Color_Off} is not configured. Cannot start without proxying anything"
    exit 255
fi

if [ -z "${DOWNSTREAM_SERVICE_NETWORK_ADDR}" ]; then
    echo -e "${BRed}ERROR:${Color_Off}The environment variable ${BRed}DOWNSTREAM_SERVICE_NETWORK_ADDR${Color_Off} is not configured. Cannot start without proxying anything"
    exit 255
fi

DEFAULT_DOWNSTREAM_SERVICE_CONNECT_ATTEMPT=15
if [ -z "${DOWNSTREAM_SERVICE_CONNECT_ATTEMPT}" ]; then
    echo -e "${BGreen}INFO: ${Color_Off}The environment variable ${BGreen}DOWNSTREAM_SERVICE_CONNECT_ATTEMPT${Color_Off} is not configured. Default value will be used: ${BGreen}${DEFAULT_DOWNSTREAM_SERVICE_CONNECT_ATTEMPT}${Color_Off}"
    DOWNSTREAM_SERVICE_CONNECT_ATTEMPT=${DEFAULT_DOWNSTREAM_SERVICE_CONNECT_ATTEMPT}
fi

echo -e "${Blue}Waiting for UPSTREAM_SERVICE: ${BBlue}${UPSTREAM_SERVICE}${Color_Off}"
SESSION_ID="`hostname`_watchdog"
pipe_in="${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/${UPSTREAM_SERVICE}/unmet_dependencies/GET/exec"
pipe_out="${SHARED_API_DIR}/${MAIN_SERVICE_NAME}/${UPSTREAM_SERVICE}/unmet_dependencies/GET/result.json_${SESSION_ID}"

declare -A SERVICE_QUERY_WATCH_PIDS
declare -A API_MANAGEMENT_PIDS

shutdown_processors_if_downstream_is_dead(){
    local downstream_server_addr=${1}
    declare -A SERV_TO_STOP
    for service_query in "${!SERVICE_QUERY_WATCH_PIDS[@]}"
    do
        query=$(sed -n 's/\(echo \"CLI SERVER: \)\(.*\)\(\"\)/\2/p' "${service_query}")
        #local url="${downstream_server_addr}/${SHARED_API_DIR}/${query}"
        local url="${downstream_server_addr}/${query}"
        echo -e "check availability of ${url}:"

        if curl --output /dev/null --silent --head --fail "$url"; then
            echo -e "${url} ${BBlue}is alive${Color_Off}"
        else
            echo -e "${url} ${BRed}is unavailable${Color_Off}. Stop proxy for the ${service_query}"
            SERV_TO_STOP[${service_query}]=${SERVICE_QUERY_WATCH_PIDS[${service_query}]}

            unset SERVICE_QUERY_WATCH_PIDS[${service_query}]
        fi
    done
    if [ ${#SERV_TO_STOP[@]} -ne 0 ] ; then
        declare -A PID_TO_STOP
        for service_query in "${!SERV_TO_STOP[@]}"
        do
            echo "match service_query: ${service_query}"
            for service in "${!API_MANAGEMENT_PIDS[@]}"
            do
                echo "for service: ${service}"
                if [[ $service_query == *"${service}/generated"* ]]; then
                    PID_TO_STOP[${service}]=${API_MANAGEMENT_PIDS[${service}]}
                fi
            done
        done

        gracefull_shutdown_bunch SERV_TO_STOP PID_TO_STOP

        for service in "${!PID_TO_STOP[@]}"
        do
            unset API_MANAGEMENT_PIDS[${service}]
            echo "Remove service launching script: ${service} from proxy list"
            rm -rf ${service}
        done

        echo "take API fs postmortem snapshot"
        echo "SHAPSHOT: $(date +%D%_H:%M:%S:%3N)" >> /tmp/fs_api_snapshot
        ls -laR ${SHARED_API_DIR} >> /tmp/fs_api_snapshot
    fi
}

termination_handler(){
    gracefull_shutdown_bunch SERVICE_QUERY_WATCH_PIDS API_MANAGEMENT_PIDS
}
echo "Setup signal handlers"
trap 'termination_handler' SIGHUP SIGQUIT SIGABRT SIGKILL SIGALRM SIGTERM EXIT

shopt -s extglob
RETURN_STATUS=0
TIMEOUT_ON_FAILURE_SEC=1
UPSTREAM_SERVICE_HEARTBEAT_SEC=15

# TODO separate cases: Downstram down & Upstream down too
API_UPDATE_EVENT_TIMEOUT_LIMIT=${DOWNSTREAM_SERVICE_CONNECT_ATTEMPT}
API_UPDATE_EVENT_TIMEOUT_COUNTER=0

rm -rf to_proxy
rm -rf to_proxy_new
if [ ! -d "to_proxy" ]; then
    # make empty directory to fill it in by newly detected services
    mkdir -m 777 to_proxy
fi
local PROXYING_API_QUERIES
while [ ${API_UPDATE_EVENT_TIMEOUT_COUNTER} != ${API_UPDATE_EVENT_TIMEOUT_LIMIT} ]; do
    # wait until downstream service become alive..
    curl --output /dev/null --silent --head --fail "${DOWNSTREAM_SERVICE_NETWORK_ADDR}"
    if (( $? )) ; then
        echo -e "${BPurple}Downstream service: ${DOWNSTREAM_SERVICE} is unavailable by addr: ${DOWNSTREAM_SERVICE_NETWORK_ADDR}${Color_Off}, trying again in attempt: ${BPurple}(${API_UPDATE_EVENT_TIMEOUT_COUNTER}/${API_UPDATE_EVENT_TIMEOUT_LIMIT})${Color_Off}"
        echo "SERVICE_QUERY_WATCH_PIDS before: ${SERVICE_QUERY_WATCH_PIDS[@]}, API_MANAGEMENT_PIDS before: ${API_MANAGEMENT_PIDS[@]}"
        shutdown_processors_if_downstream_is_dead ${DOWNSTREAM_SERVICE_NETWORK_ADDR}
        echo "SERVICE_QUERY_WATCH_PIDS after: ${SERVICE_QUERY_WATCH_PIDS[@]}, API_MANAGEMENT_PIDS after: ${API_MANAGEMENT_PIDS[@]}"

        sleep ${TIMEOUT_ON_FAILURE_SEC} &
        wait $!
        let API_UPDATE_EVENT_TIMEOUT_COUNTER=${API_UPDATE_EVENT_TIMEOUT_COUNTER}+1
        continue
    fi

    # wait until upstream service become alive...
    send_ka_watchdog_query ${pipe_in} ${SESSION_ID} ${DOWNSTREAM_SERVICE} 5
    if [ $? -ne 0 ]; then
        echo -e "${BRed}Heartbeat query: ${pipe_in} has stuck on${Color_Off} probably due to ${BRed}${UPSTREAM_SERVICE}${Color_Off} outage, trying again in attempt: ${BRed}(${API_UPDATE_EVENT_TIMEOUT_COUNTER}/${API_UPDATE_EVENT_TIMEOUT_LIMIT})${Color_Off}"
        let API_UPDATE_EVENT_TIMEOUT_COUNTER=${API_UPDATE_EVENT_TIMEOUT_COUNTER}+1
        sleep ${TIMEOUT_ON_FAILURE_SEC} &
        wait $!
        continue
    fi
    PROXYING_API_QUERIES=
    receive_ka_watchdog_query ${pipe_out} 5 PROXYING_API_QUERIES
    if [ $? -ne 0 ]; then
        echo -e "${BRed}Heartbeat query: ${pipe_out} has stuck on${Color_Off} probably due to ${BRed}${UPSTREAM_SERVICE}${Color_Off} outage, trying again in attempt: ${BRed}(${API_UPDATE_EVENT_TIMEOUT_COUNTER}/${API_UPDATE_EVENT_TIMEOUT_LIMIT})${Color_Off}"
        let API_UPDATE_EVENT_TIMEOUT_COUNTER=${API_UPDATE_EVENT_TIMEOUT_COUNTER}+1
        continue
    fi

    if [ -z "${PROXYING_API_QUERIES}" ]; then

        echo "SERVICE_QUERY_WATCH_PIDS before: ${SERVICE_QUERY_WATCH_PIDS[@]}, API_MANAGEMENT_PIDS before: ${API_MANAGEMENT_PIDS[@]}"
        shutdown_processors_if_downstream_is_dead ${DOWNSTREAM_SERVICE_NETWORK_ADDR}
        echo "SERVICE_QUERY_WATCH_PIDS after: ${SERVICE_QUERY_WATCH_PIDS[@]}, API_MANAGEMENT_PIDS after: ${API_MANAGEMENT_PIDS[@]}"
        sleep ${UPSTREAM_SERVICE_HEARTBEAT_SEC} &
        wait $!
        continue
    fi

    let API_UPDATE_EVENT_TIMEOUT_COUNTER=0
    echo -e "${Green}Upstream service: ${BGreen}${UPSTREAM_SERVICE}${Green} got dependencies changed: ${BGreen}${PROXYING_API_QUERIES}${Color_Off}"
    rm -rf to_proxy_new
    ./serialize_unmet_deps_into_schema_files.py "${PROXYING_API_QUERIES}" "to_proxy_new"

    if [ ! -d to_proxy_new ]; then
        echo -e "${Red}Cannot serialize deps ${BRed}${PROXYING_API_QUERIES}${Red} into schema files! Try again...${Color_Off}"
        continue
    fi
    # compare files
    declare -A SERVICE_TO_STOP
    declare -A API_MANAGEMENT_PIDS_TO_STOP
    declare -A SERVICE_TO_RUN
    SERVICE_TO_STOP=()
    API_MANAGEMENT_PIDS_TO_STOP=()
    SERVICE_TO_RUN=()
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
            if [ ! -z ${SERVICE_QUERY_WATCH_PIDS[${OLD_SERVICE_FILE_PATH}]} ] ; then
                SERVICE_TO_STOP[${OLD_SERVICE_FILE_PATH}]=${SERVICE_QUERY_WATCH_PIDS[${OLD_SERVICE_FILE_PATH}]}
                rm ${OLD_SERVICE_FILE_PATH}
            fi
            unset SERVICE_QUERY_WATCH_PIDS[${OLD_SERVICE_FILE_PATH}]

            if [ ! -z ${API_MANAGEMENT_PIDS[${OLD_SERVICE_FILE_PATH}]} ] ; then
                API_MANAGEMENT_PIDS_TO_STOP[${OLD_SERVICE_FILE_PATH}]=${OLD_SERVICE_FILE_PATH[${OLD_SERVICE_FILE_PATH}]}
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
    echo "take API fs snapshot after services shutdown"
    echo "SHAPSHOT: `date +%D_%H:%M:%S:%3N`" >> /tmp/fs_api_snapshot
    ls -laR ${SHARED_API_DIR} >> /tmp/fs_api_snapshot

    echo -e "${BBlue}Launch new services${Color_Off}, which ${UPSTREAM_SERVICE} has become depend on: ${!SERVICE_TO_RUN[@]}"
    for service in "${!SERVICE_TO_RUN[@]}"
    do
        echo -e "Generate proxy for ${BBlue}${service}${Color_Off}:"
        ./build_proxy_services.py "${service}" -os "${service}/generated" -oe "${service}/exec_generated"
        ${OPT_DIR}/build_api_pseudo_fs.py "${service}" ${SHARED_API_DIR}

        # for each 'service' launch all its query-servers
        launch_fs_api_services SERVICE_QUERY_WATCH_PIDS "${service}/generated"

        #### TODO - make api_management for individual query!!!
        ${OPT_DIR}/api_management.py "${service}" ${MAIN_SERVICE_NAME} ${SHARED_API_DIR} &
        API_MANAGEMENT_PIDS[${service}]=$!
    done
done

termination_handler
echo "Exit with code: ${RETURN_STATUS}"
exit ${RETURN_STATUS}
