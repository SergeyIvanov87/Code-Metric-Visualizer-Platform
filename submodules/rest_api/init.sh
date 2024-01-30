#!/usr/bin/bash

WORK_DIR=${1}
INITIAL_PROJECT_LOCATION=${2}
SHARED_API_DIR=${2}/api.pmccabe_collector.restapi.org
MAIN_IMAGE_ENV_SHARED_LOCATION=${3}

mkdir -p ${SHARED_API_DIR}
${WORK_DIR}/parse_api_pseudo_fs.py ${SHARED_API_DIR} ${WORK_DIR}/API

rm -f ${WORK_DIR}/rest_api_server/rest_api_server/cgi.py
cp ${WORK_DIR}/rest_api_server/rest_api_server/cgi_template.py ${WORK_DIR}/rest_api_server/rest_api_server/cgi.py
${WORK_DIR}/build_api_cgi.py ${WORK_DIR}/API api.pmccabe_collector.restapi.org >> ${WORK_DIR}/rest_api_server/rest_api_server/cgi.py
cd ${WORK_DIR}/rest_api_server/

echo "DEBUG CMD:  cp ../rest_api_server/rest_api_server/cgi_template.py ../rest_api_server/rest_api_server/cgi.py && ../build_api_cgi.py ../API api.pmccabe_collector.restapi.org >> ../rest_api_server/rest_api_server/cgi.py"
pipx install -e .
flask --app rest_api_server run --host 0.0.0.0

sleep infinity
