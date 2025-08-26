#!/bin/bash

test_suite_filename=${0}

oneTimeSetUp() {
    read -r -d '' EXEC_STR << EOM
from api_fs_exec_utils import *

print('test_function() {\n',
      *[ l+"\n" for l in generate_api_node_env_init()],
      *[ l+"\n" for l in generate_read_api_fs_args()],
      '\n}\n',
      *[ l+"\n" for l in generate_bypassed_params_formatting()])
EOM
    python -c "${EXEC_STR}" > ${test_suite_filename}_impl.sh
    source ${test_suite_filename}_impl.sh
}

oneTimeTearDown() {
    if [ -f ${test_suite_filename}_impl.sh ]; then
        rm ${test_suite_filename}_impl.sh
    fi
}

TEST_API_NODE="/tmp/tests_sandbox_`date +%H%M%S`"
declare -A TEST_PARAM_VALUE_MAP

setUp() {
    TEST_API_NODE="${TEST_API_NODE}/api_node_`date +%H%M%S`"
    mkdir -p ${TEST_API_NODE}

    TEST_PARAM_VALUE_MAP["-param_a"]="value_00"
    TEST_PARAM_VALUE_MAP["--param_b"]="value_01"
    TEST_PARAM_VALUE_MAP["--param_c"]="value_02"
    for p in ${!TEST_PARAM_VALUE_MAP[@]}; do
        echo ${TEST_PARAM_VALUE_MAP[${p}]} > "${TEST_API_NODE}/00.${p}"
    done
}

tearDown() {
    if [ ! -z ${TEST_API_NODE} ] && [ -d  ${TEST_API_NODE} ]; then
        rm -r ${TEST_API_NODE}
    fi

    for p in ${!TEST_PARAM_VALUE_MAP[@]}; do
        unset TEST_PARAM_VALUE_MAP[${p}]
    done
}

overrided_cmd_args_to_array() {
    prev_file=

    # nameref for indirection
    local -n out_array=${1}
    for file in ${OVERRIDEN_CMD_ARGS[@]};
    do
      if [ -z $prev_file ]; then
        prev_file=${file}
      else
        out_array[${prev_file}]=${file}
        prev_file=
      fi
    done
}

test_all_files() {

    test_function "${TEST_API_NODE}" "bbb"
    echo "API_NODE: ${API_NODE}"
    declare -A ARRAY
    overrided_cmd_args_to_array ARRAY
    for file in ${!ARRAY[@]};
    do
       assertEquals ${TEST_PARAM_VALUE_MAP[$file]} ${ARRAY[$file]}
    done
}


. shunit2
