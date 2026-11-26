#!/bin/bash

test_suite_filename=${0}

oneTimeSetUp() {
    read -r -d '' EXEC_STR << EOM
from api_fs_exec_utils import *
from api_fs_bash_utils import *

print(
      *[ l+"\n" for l in generate_split_quoted_arguments()],
      '\n',
      'test_function() {\n',
      *[ l+"\n" for l in generate_api_node_env_init()],
      *[ l+"\n" for l in generate_read_api_fs_args()],
      '    parsed_args=("\${OVERRIDEN_CMD_ARGS[@]}")',
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
    for p in "${!TEST_PARAM_VALUE_MAP[@]}"; do
        echo ${TEST_PARAM_VALUE_MAP[${p}]} > "${TEST_API_NODE}/00.${p}"
    done
}

tearDown() {
    if [ ! -z ${TEST_API_NODE} ] && [ -d  ${TEST_API_NODE} ]; then
        rm -r ${TEST_API_NODE}
    fi

    for p in "${!TEST_PARAM_VALUE_MAP[@]}"; do
        unset TEST_PARAM_VALUE_MAP[${p}]
    done
}

overrided_cmd_args_to_array() {
    prev_file=

    # nameref for indirection
    local -n out_array=${1}
    for file in "${parsed_args[@]}";
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
    local -a parsed_args=()

    test_function "${TEST_API_NODE}" "bbb"
    assertEquals 6 "${#parsed_args[@]}"
    echo "API_NODE: ${API_NODE}"
    declare -A ARRAY
    overrided_cmd_args_to_array ARRAY
    for file in "${!ARRAY[@]}";
    do
       assertEquals ${TEST_PARAM_VALUE_MAP[$file]} ${ARRAY[$file]}
    done
}


test_ignores_markdown_and_fifo_log_extensions() {
    local -a parsed_args=()

    touch "${TEST_API_NODE}"/{README.md,123456789012.log,123456789012.log.lock,123456789012.log.1,123456789012.log.12,fifo_transactions.log.261126_123456}
    printf '%s\n' positional > "${TEST_API_NODE}/01.NO_NAME_PARAM.1"

    test_function "${TEST_API_NODE}" "bbb"

    assertEquals 7 "${#parsed_args[@]}"
    assertEquals positional "${parsed_args[6]}"
}

. shunit2
