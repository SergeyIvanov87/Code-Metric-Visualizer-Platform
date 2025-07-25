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

HOSTNAME_IP_FILE=/package/hostname_ip
POPULATED_HOSTNAME_IP_FILE=${SHARED_API_DIR}/rest_api_addr

remove_populated_host_ip_file(){
    trap - EXIT

    echo "${LOG_PREFIX}Cleanup: ${POPULATED_HOSTNAME_IP_FILE}"
    if [ -f ${POPULATED_HOSTNAME_IP_FILE} ] ; then
        rm -f ${POPULATED_HOSTNAME_IP_FILE}
    fi
}

populate_host_ip_file(){
    ln -sf ${HOSTNAME_IP_FILE} ${POPULATED_HOSTNAME_IP_FILE}
}

termination_handler(){
   echo -e "${BRed}***Stopping${Color_Off}"
   remove_populated_host_ip_file
   exit 0
}

echo "Setup signal handlers"
trap 'termination_handler' SIGHUP SIGQUIT SIGABRT SIGKILL SIGALRM SIGTERM EXIT

echo "DEBUG CMD:"
echo "cp ../rest_api_server/rest_api_server/cgi_template.py ../rest_api_server/rest_api_server/cgi.py && ../build_api_cgi.py ../restored_API /api api.pmccabe_collector.restapi.org >> ../rest_api_server/rest_api_server/cgi.py"
echo "flask --app rest_api_server run --host 0.0.0.0"

# Launch REST_API server in an infinitive loop:
# It must be started before any inotify event has been listened,
# so when earlier event was arrived, we would process that
export REST_API_INSTANCE_PIDFILE=${MY_FLASK_INSTANCE_PIDFILE}
/package/watchdog_server.sh ${REST_API_INSTANCE_PIDFILE} ${FLASK_RUN_HOST} ${FLASK_RUN_PORT} ${HOSTNAME_IP_FILE} ${WAIT_FOR_API_SERVICE_PROVIDER_INITIALIZED_ATTEMPTS} ${WAIT_FOR_API_SERVICE_PROVIDER_STARTED_ATTEMPTS} ${WAIT_FOR_SERVER_STARTING_LIMIT_SEC} &
WATCHDOG_PID=$!

shopt -s extglob
RETURN_STATUS=0
API_UPDATE_EVENT_TIMEOUT_SEC=1
API_UPDATE_EVENT_TIMEOUT_LIMIT=3
API_UPDATE_EVENT_TIMEOUT_COUNTER=0
# Loop until any unrecoverable error would occur
HAS_GOT_API_UPDATE_EVENT=0
LAST_TIME_README_FILES_DETECTED_COUNT=0
while [ $RETURN_STATUS -eq 0 ]; do
        # Handle the chain-reaction of API *md files creation.
        # It occurs when multiple services are starting simultaneously and populating their API and that will trigger
        # REST_API service down-up every time when standalone *md file is published.
        # To deal with that situation, the algorithm collect all events during timeout and process a final bundle
        # to restart REST_API only once
        let API_UPDATE_EVENT_TIMEOUT_COUNTER=0
        while [ $API_UPDATE_EVENT_TIMEOUT_COUNTER -le $API_UPDATE_EVENT_TIMEOUT_LIMIT ]; do
            # Algorithm modifies RETURN_STATUS variable inside this inner loop, which would have been a different subshell if we have launched it in
            # a accustomed way like:
            #
            #      inotifywait -mr ${SHARED_API_DIR} -e modify,create,delete --include '.md$' | while read dir action file; do
            #
            # This pipelining "|" creates a new subshell actually, hence given RETURN_STATUS variable would not be changed in the main script rather than its duplicate in a subshell.
            # To overcome this limitation It had better use `here string` https://www.gnu.org/savannah-checkouts/gnu/bash/manual/bash.html#Here-Strings,
            # which allow us to execute this inner loop in the main shell context so that modification of RETURN_STATUS will be visible here
            # and allow this watching algorithm to be stopped by emergency
            while read dir action file; do
                case "$action" in
                    CREATE|DELETE|MODIFY|MOVE_TO|MOVE_FROM )
                        let HAS_GOT_API_UPDATE_EVENT=$HAS_GOT_API_UPDATE_EVENT+1
                        # reset timeout counter upon event emerging
                        let API_UPDATE_EVENT_TIMEOUT_COUNTER=0
                        echo -e "${BBlue}Event has been detected:${Color_Off} ${file}, action; ${action}, dir: ${dir}. ${BBlue}Reconfigure REST_API Service....${Color_Off}"
                        ;;
                    *)
                        # do not spam air by any timeout info here!
                        ;;
                esac
            done <<< "$(inotifywait -rq ${SHARED_API_DIR} -e modify,create,delete -t ${API_UPDATE_EVENT_TIMEOUT_SEC} --include '.md$' )"

            # as do not observe inotify constantly, it's possible that new README file would appear unattended.
            # In this case this safeguard introduced: we keep counting an amount of README files so that we are still able to detect API changing
            if [ ${HAS_GOT_API_UPDATE_EVENT} == 0 ];
            then
                md_files_new_count=`ls -laR ${SHARED_API_DIR} | grep md | wc -l`
                if [ ${LAST_TIME_README_FILES_DETECTED_COUNT} != ${md_files_new_count} ];
                then
                    echo -e "${BBlue} README files mount has been changed, was: ${LAST_TIME_README_FILES_DETECTED_COUNT}, become: ${md_files_new_count}. Generate event manually${Color_Off}"
                    let HAS_GOT_API_UPDATE_EVENT=$HAS_GOT_API_UPDATE_EVENT+1
                fi
            fi
            let API_UPDATE_EVENT_TIMEOUT_COUNTER=$API_UPDATE_EVENT_TIMEOUT_COUNTER+1
        done
        # In general, it must restart a running server instance by sending SIGTERM to its PID.
        # PID is expected to be stored in REST_API_INSTANCE_PIDFILE.
        # This file cannot appear instantly, as well as a REST_API server instance recreated, thus we check for this file reappearance.
        # The situation is more accute when events occured rapidly...
        # Therefore to be consistent, It had better make light checks only until the service starts without waiting this uninterruptibly.

        # By the way, as an unpredictable error in launching the new server instance may occured,
        # hence the algorithm will test additionally whether WATCHDOG is alive.
        # If the WATCHDOG is alive and the SERVER is dead then the former can handle the situation or gives SERVER an another attempt,
        # Thus, we is about to continue waiting for REST_API service uprising, unless
        # WATCHDOG is dead itself. Once the both WATCHDOG and SERVER are dead, this container became inoperable
        if [ ! -f ${REST_API_INSTANCE_PIDFILE} ]; then
            kill -s 0 ${WATCHDOG_PID} > /dev/null 2>&1
            WATCHDOG_TEST_RESULT=$?
            if [ $WATCHDOG_TEST_RESULT != 0 ]; then
                echo -e "${BRed}Unrecoverable error has occured. Container is inoperable. Abort.${Color_Off}"
                remove_populated_host_ip_file
                RETURN_STATUS=255
                break
            fi
            echo "The server hasn't started yet..."
            continue
        else
            populate_host_ip_file
        fi

        # Restart the running service instance only if API has been changed
        if [ ${HAS_GOT_API_UPDATE_EVENT} -gt 0 ]; then
            echo -e "Got ${HAS_GOT_API_UPDATE_EVENT} API events. ${BBlue}Restart REST_API service will be scheduled...${Color_Off}"
            # remember last count of README files
            LAST_TIME_README_FILES_DETECTED_COUNT=`ls -laR ${SHARED_API_DIR} | grep md | wc -l`
            # kill an old instance
            remove_populated_host_ip_file
            REST_API_INSTANCE_PIDFILE_PID=`cat ${REST_API_INSTANCE_PIDFILE}`
            kill -s SIGINT ${REST_API_INSTANCE_PIDFILE_PID}
            while [ -f ${REST_API_INSTANCE_PIDFILE} ]; do
                sleep 0.1
                kill -s SIGINT ${REST_API_INSTANCE_PIDFILE_PID}
                echo "Waiting for a server to stop, pid ${REST_API_INSTANCE_PIDFILE_PID}..."
            done
            echo "The server stopped, last detected README files count: ${LAST_TIME_README_FILES_DETECTED_COUNT}"

            # reset event counter
            HAS_GOT_API_UPDATE_EVENT=0
        fi
done

if [ ! -z ${WATCHDOG_PID} ] && [ ${WATCHDOG_PID} != 0 ]; then
    echo "Wait for watchdog finished"
    wait ${WATCHDOG_PID}
fi

remove_populated_host_ip_file
echo "Exit with code: ${RETURN_STATUS}"
exit ${RETURN_STATUS}
