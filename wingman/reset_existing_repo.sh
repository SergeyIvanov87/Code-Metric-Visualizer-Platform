#!/usr/bin/bash

. /package/setenv.sh

cd ${REPO_PATH}
git reset --hard origin/${REPO_BRANCH}

