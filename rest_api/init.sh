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

/package/watchdog_server.sh &
WATCHDOG_PID=$!

shopt -s extglob
while :
do
    inotifywait -mr ${SHARED_API_DIR} -e modify,create,delete --include '.md$' |
        while read dir action file; do
            echo "event has happened: ${file}, action; ${action}, dir: ${dir}"
            case "$action" in
                CREATE|DELETE|MODIFY )
                    date=`date +%Y-%m-%dT%H:%M:%S`
                    echo "file changed ${file}"
                    killall python
                    ;;
                *)
                    ;;
            esac
        done
done
wait ${WATCHDOG_PID}
