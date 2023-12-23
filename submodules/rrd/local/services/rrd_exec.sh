#!/usr/bin/bash

API_NODE=${1}
. $2/setenv.sh
RESULT_FILE=${3}_result
CMD_ARGS=""
for entry in "${API_NODE}"/*.*
do
    file_basename=${entry##*/}
    param_name=${file_basename#*.}
    readarray -t arr < ${entry}
    special_kind_param_name=${param_name%.*}
    if [[ ${special_kind_param_name} != 'NO_NAME_PARAM' ]];
    then
        brr+=(${param_name})
    fi
    for a in ${arr[@]}
    do
        if [[ ${a} == \"* ]];
        then
            brr+=("${a}")
        else
            brr+=(${a})
        fi
    done
done
echo "${brr[@]}"
