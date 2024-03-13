#!/bin/bash

WORK_DIR=${1}
MAIN_IMAGE_ENV_SHARED_LOCATION=${2}
INITIAL_PROJECT_LOCATION=/mnt
SHARED_API_DIR=${3}

echo -e "#!/bash\n\nexport WORK_DIR=${WORK_DIR} \nexport MAIN_IMAGE_ENV_SHARED_LOCATION=${MAIN_IMAGE_ENV_SHARED_LOCATION} \nexport SHARED_DIR=${SHARED_DIR} \nexport SHARED_API_DIR=${SHARED_API_DIR} \nexport INITIAL_PROJECT_LOCATION=${INITIAL_PROJECT_LOCATION} \nexport RRD_ROOT=${SHARED_API_DIR}" > ${MAIN_IMAGE_ENV_SHARED_LOCATION}/setenv.sh

# allow pmccabe_collector to access reposiroty
git clone ${PROJECT_URL} -b ${PROJECT_BRANCH} ${INITIAL_PROJECT_LOCATION}

# start crontab
echo "${CRON_REPO_UPDATE_SCHEDULE} cd ${INITIAL_PROJECT_LOCATION} && git pull origin ${PROJECT_BRANCH}" > daily_pull
crontab daily_pull
crond -b -l 0 -d 0

# create API directory and initialize API nodes
mkdir -p ${SHARED_API_DIR}
${MAIN_IMAGE_ENV_SHARED_LOCATION}/build_api_executors.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}
${MAIN_IMAGE_ENV_SHARED_LOCATION}/build_api_services.py ${WORK_DIR}/API ${WORK_DIR} -o ${WORK_DIR}/services
${MAIN_IMAGE_ENV_SHARED_LOCATION}/build_api_pseudo_fs.py ${WORK_DIR}/API ${SHARED_API_DIR}
${MAIN_IMAGE_ENV_SHARED_LOCATION}/make_api_readme.py ${WORK_DIR}/API > ${SHARED_API_DIR}/api.pmccabe_collector.restapi.org/project/README-API-STATISTIC.md

echo "run API listeners:"
for s in ${WORK_DIR}/services/*.sh; do
    ${s} ${MAIN_IMAGE_ENV_SHARED_LOCATION} &
    echo "${s} has been started"
done

sleep infinity
