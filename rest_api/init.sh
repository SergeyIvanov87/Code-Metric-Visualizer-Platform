#!/bin/bash

export WORK_DIR=${1}
export OPT_DIR=${2}
export PYTHONPATH="${2}:${2}/modules"
export SHARED_API_DIR=${3}
export MAIN_SERVICE_NAME=api.pmccabe_collector.restapi.org

# use source this script as fast way to setup environment for debugging
echo -e "export WORK_DIR=${WORK_DIR}\nexport OPT_DIR=${OPT_DIR}\nexport SHARED_API_DIR=${SHARED_API_DIR}\nexport MAIN_SERVICE_NAME=${MAIN_SERVICE_NAME}\nexport PYTHONPATH=${PYTHONPATH}" > ${WORK_DIR}/env.sh

termination_handler(){
   echo "***Stopping"
   exit 0
}

echo "Setup signal handlers"
trap 'termination_handler' SIGTERM

echo "DEBUG CMD:"
echo "cp ../rest_api_server/rest_api_server/cgi_template.py ../rest_api_server/rest_api_server/cgi.py && ../build_api_cgi.py ../restored_API /api api.pmccabe_collector.restapi.org >> ../rest_api_server/rest_api_server/cgi.py"
echo "flask --app rest_api_server run --host 0.0.0.0"

# Launch REST_API server in an infinitive loop:
# It must be started before any inotify event has been listened,
# so when earlier event was arrived, we would process that
export REST_API_INSTANCE_PIDFILE=${MY_FLASK_INSTANCE_PIDFILE}
/package/watchdog_server.sh ${REST_API_INSTANCE_PIDFILE} ${FLASK_RUN_HOST} ${FLASK_RUN_PORT} &
WATCHDOG_PID=$!

shopt -s extglob
RETURN_STATUS=0
API_UPDATE_EVENT_TIMEOUT_SEC=1
API_UPDATE_EVENT_TIMEOUT_LIMIT=3
API_UPDATE_EVENT_TIMEOUT_COUNTER=0
# Loop until any unrecoverable error would occur
while [ $RETURN_STATUS -eq 0 ]; do
        HAS_GOT_API_UPDATE_EVENT=0

        # Handle the chain-reaction of API *md files creation.
        # It occurs when multiple services are starting simultaneously and populating their API and that will trigger
        # REST_API service down-up every time when standalone *md file is published.
        # To deal with that situation, the algorithm collect all events during timeout and process a final bundle
        # to restart REST_API only once
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
                    CREATE|DELETE|MODIFY )
                        let HAS_GOT_API_UPDATE_EVENT=$HAS_GOT_API_UPDATE_EVENT+1
                        let API_UPDATE_EVENT_TIMEOUT_COUNTER=0
                        echo "Event has been detected: ${file}, action; ${action}, dir: ${dir}. Reconfigure REST_API Service...."
                        ;;
                    *)
                        # do not spam air by any timeout info here!
                        ;;
                esac
            done <<< "$(inotifywait -rq ${SHARED_API_DIR} -e modify,create,delete -t ${API_UPDATE_EVENT_TIMEOUT_SEC} --include '.md$' )"
            let API_UPDATE_EVENT_TIMEOUT_COUNTER=$API_UPDATE_EVENT_TIMEOUT_COUNTER+1
        done
        let API_UPDATE_EVENT_TIMEOUT_COUNTER=0
        # In general, it must restart a running server instance by sending SIGTERM to its PID.
        # PID is expected to be stored in REST_API_INSTANCE_PIDFILE.
        # This file cannot appear instantly, as well as a REST_API server instance recreated, thus we wait for this file appearance.
        # The situation is more accute when events occured rapidly...
        # Therefore to be consistent, It had better wait until the service starts.

        # By the way, through an unpredictable error in launching the new server instance may occureded
        # to avoid waiting forever, it is OK untill it checks whether WATCHDOG is alive.
        # If WATCHDOG is alive then it can handle the situation or gives another try,
        # we is about to continue waiting for REST_API service uprising, unless
        # WATCHDOG is dead itself. Once the service is dead, this container became inoperable
        while [ ! -f ${REST_API_INSTANCE_PIDFILE} ]; do
            kill -s 0 ${WATCHDOG_PID} > /dev/null 2>&1
            WATCHDOG_TEST_RESULT=$?
            if [ $WATCHDOG_TEST_RESULT != 0 ]; then
                echo "Unrecoverable error has occured. Container is inoperable. Abort."
                RETURN_STATUS=255
                break
            fi
            echo "Waiting for a server to start..."
            sleep 1;
        done

        # Restart the running service instance only if API has been changed
        if [ ${HAS_GOT_API_UPDATE_EVENT} -gt 0 ]; then
            echo "Got ${HAS_GOT_API_UPDATE_EVENT} API events. Restart REST_API service will be scheduled..."
            # kill an old instance
            REST_API_INSTANCE_PIDFILE_PID=`cat ${REST_API_INSTANCE_PIDFILE}`
            kill -s SIGTERM ${REST_API_INSTANCE_PIDFILE_PID}
            while [ -f ${REST_API_INSTANCE_PIDFILE} ]; do
                sleep 0.1
                echo "Waiting for a server to stop, pid ${REST_API_INSTANCE_PIDFILE_PID}..."
            done
            # wait for a new instance to start and also make sure than WATCHDOG is alive so that
            # no any unrecoverable erro has occured.
            # If we omit thsi check than next WATCHDOG & service cheking will happen up on another
            # inotify event has come, which may be unreachable.
            # The solution might be introducing inotify timeout instead, but using that
            # we might miss events occured during that timeout
            while [ ! -f ${REST_API_INSTANCE_PIDFILE} ]; do
                kill -s 0 ${WATCHDOG_PID} > /dev/null 2>&1
                WATCHDOG_TEST_RESULT=$?
                if [ $WATCHDOG_TEST_RESULT != 0 ]; then
                    echo "Unrecoverable error has occured. Container is inoperable. Abort."
                    WATCHDOG_PID=0
                    RETURN_STATUS=255
                    break
                fi
                echo "Waiting for a new server instance to start..."
                sleep 1;
            done
        fi
done

if [ ! -z ${WATCHDOG_PID} ] && [ ${WATCHDOG_PID} != 0 ]; then
    echo "Wait for watchdog finished"
    wait ${WATCHDOG_PID}
fi
echo "Exit with code: ${RETURN_STATUS}"
exit ${RETURN_STATUS}
