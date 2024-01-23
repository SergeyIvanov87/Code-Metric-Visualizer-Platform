#!/usr/bin/bash

WORK_DIR=${1}
INITIAL_PROJECT_LOCATION=${2}
SHARED_API_DIR=${2}/api.pmccabe_collector.restapi.org
MAIN_IMAGE_ENV_SHARED_LOCATION=${3}

flask --app server run --host 0.0.0.0

sleep infinity
