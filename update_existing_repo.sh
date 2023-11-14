#!/usr/bin/bash

. /package/setenv.sh

cd ${REPO_PATH}
git pull origin
git reset --hard origin/${REPO_BRANCH}
