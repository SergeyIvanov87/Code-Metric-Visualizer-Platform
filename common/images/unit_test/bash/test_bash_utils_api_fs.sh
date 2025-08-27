#!/bin/bash

test_suite_filename=${0}

oneTimeSetUp() {
    read -r -d '' EXEC_STR << EOM
from api_fs_bash_utils import *

print(*generate_exec_watchdog_function(),
      *generate_extract_attr_value_from_string(),
      *generate_add_suffix_if_exist(),
      *generate_wait_until_pipe_exist(),
      *generate_unblock_query_pipe_writers_by_owner(),
      *generate_unblock_result_pipe_reader_by_owner(),
      *generate_unblock_readers_of_result_pipe_array_by_owner()
)
EOM
    python -c "${EXEC_STR}" > ${test_suite_filename}_impl.sh
    source ${test_suite_filename}_impl.sh
}

oneTimeTearDown() {
    if [ -f ${test_suite_filename}_impl.sh ]; then
        rm ${test_suite_filename}_impl.sh
    fi
}

test_watchdog() {
    PIPE_NAME=/tmp/test_watchdog_pipe`date +%H%M%S`
    mkfifo -m 644 ${PIPE_NAME}
    (echo 0 > ${PIPE_NAME}) &
    PID=$!
    assertEquals `ps -ef | grep ${PID} | grep -v grep | wc -l` 1
    exec_watchdog ${PID} ${PIPE_NAME}
    assertEquals "must be unblocked" `ps -ef | grep ${PID} | grep -v grep | wc -l` 0
}

test_extract_avp_from_string_or_default() {
    local INPUT_STRING="the string that has no parameters"
    local PARAM_TO_SEARCH="SESSION_ID"
    extract_avp_from_string_or_default ${PARAM_TO_SEARCH} "${INPUT_STRING}" "" '=' SESSION_ID_VALUE
    if [ -z ${SESSION_ID_VALUE} ]; then
       echo "SESSION_ID_VALUE is empty"
       #fail "\"${INPUT_STRING}\" contains no \"${PARAM_TO_SEARCH}\", default empty is used, got empty???${SESSION_ID_VALUE}???"
    fi


    INPUT_STRING="the string that has no parameters"
    PARAM_TO_SEARCH="SESSION_ID"
    extract_avp_from_string_or_default ${PARAM_TO_SEARCH} "${INPUT_STRING}" "DefAuLtVaLuE" '=' SESSION_ID_VALUE
    assertEquals "\"${INPUT_STRING}\" contains no \"${PARAM_TO_SEARCH}\", default is used" ${SESSION_ID_VALUE} "DefAuLtVaLuE"

    PARAM_TO_SEARCH="SESSION_ID"
    INPUT_STRING="${PARAM_TO_SEARCH}=FOUND"
    extract_avp_from_string_or_default ${PARAM_TO_SEARCH} "${INPUT_STRING}" "" '=' SESSION_ID_VALUE
    assertEquals "\"${INPUT_STRING}\" \"${PARAM_TO_SEARCH}\"" ${SESSION_ID_VALUE} "FOUND"

    INPUT_STRING="${PARAM_TO_SEARCH}_VALUE_TO_SEARCH_NOT_FOUND=FOUND_BUT_MUST_NOT"
    extract_avp_from_string_or_default ${PARAM_TO_SEARCH} "${INPUT_STRING}" "DefAuLtVaLuE" '=' SESSION_ID_VALUE
    assertEquals "\"${INPUT_STRING}\" contains partial name matching \"${PARAM_TO_SEARCH}\", default is used" ${SESSION_ID_VALUE} "DefAuLtVaLuE"

    PARAM_TO_SEARCH="SESSION_ID"
    INPUT_STRING="${PARAM_TO_SEARCH}:FOUND_with_new_separator"
    extract_avp_from_string_or_default ${PARAM_TO_SEARCH} "${INPUT_STRING}" "" ':' SESSION_ID_VALUE
    assertEquals "\"${INPUT_STRING}\" \"${PARAM_TO_SEARCH}\"" ${SESSION_ID_VALUE} "FOUND_with_new_separator"

    PARAM_TO_SEARCH="SESSION_ID"
    INPUT_STRING="${PARAM_TO_SEARCH}=FOUND_first PARAM_NOT_TO_SEARCH=VALUE"
    extract_avp_from_string_or_default ${PARAM_TO_SEARCH} "${INPUT_STRING}" "" '=' SESSION_ID_VALUE
    assertEquals "\"${INPUT_STRING}\" \"${PARAM_TO_SEARCH}\"" ${SESSION_ID_VALUE} "FOUND_first"

    PARAM_TO_SEARCH="SESSION_ID"
    INPUT_STRING="PARAM_NOT_TO_SEARCH=VALUE ${PARAM_TO_SEARCH}=FOUND_second"
    extract_avp_from_string_or_default ${PARAM_TO_SEARCH} "${INPUT_STRING}" "" '=' SESSION_ID_VALUE
    assertEquals "\"${INPUT_STRING}\" \"${PARAM_TO_SEARCH}\"" ${SESSION_ID_VALUE} "FOUND_second"

    PARAM_TO_SEARCH="SESSION_ID"
    INPUT_STRING="PARAM_NOT_TO_SEARCH:VALUE ${PARAM_TO_SEARCH}:FOUND_second_with_another_sep"
    extract_avp_from_string_or_default ${PARAM_TO_SEARCH} "${INPUT_STRING}" "" ':' SESSION_ID_VALUE
    assertEquals "\"${INPUT_STRING}\" \"${PARAM_TO_SEARCH}\"" ${SESSION_ID_VALUE} "FOUND_second_with_another_sep"
    PARAM_TO_SEARCH="SESSION_ID"

    INPUT_STRING="PARAM_NOT_TO_SEARCH=VALUE ${PARAM_TO_SEARCH}:FOUND_second_with_mixed_sep"
    extract_avp_from_string_or_default ${PARAM_TO_SEARCH} "${INPUT_STRING}" "" ':' SESSION_ID_VALUE
    assertEquals "\"${INPUT_STRING}\" \"${PARAM_TO_SEARCH}\"" ${SESSION_ID_VALUE} "FOUND_second_with_mixed_sep"

    INPUT_STRING="PARAM_NOT_TO_SEARCH=VALUE ${PARAM_TO_SEARCH}:FOUND_second_with__invalid_sep"
    extract_avp_from_string_or_default ${PARAM_TO_SEARCH} "${INPUT_STRING}" "DEFAULT_for_invalid_sep" '-' SESSION_ID_VALUE
    assertEquals "\"${INPUT_STRING}\" \"${PARAM_TO_SEARCH}\"" ${SESSION_ID_VALUE} "DEFAULT_for_invalid_sep"
}

test_extract_avp_from_string_or_default_multiple_calls() {
    local INPUT_STRING="the string that has no parameters"
    local PARAM_0_TO_SEARCH="PARAM_0"
    local PARAM_1_TO_SEARCH="PARAM_1"
    extract_avp_from_string_or_default ${PARAM_0_TO_SEARCH} "${INPUT_STRING}" "" '=' PARAM_0_VALUE
    extract_avp_from_string_or_default ${PARAM_1_TO_SEARCH} "${INPUT_STRING}" "" '=' PARAM_1_VALUE
    if [ -z ${PARAM_0_VALUE} ]; then
       echo "PARAM_0_VALUE is empty"
       # fail "\"${INPUT_STRING}\" contains no \"${PARAM_0_TO_SEARCH}\", default empty is used, got empty???${PARAM_0_VALUE}???"
    fi
    if [ -z ${PARAM_1_VALUE} ]; then
       echo "PARAM_1_VALUE is empty"
       # fail "\"${INPUT_STRING}\" contains no \"${PARAM_1_TO_SEARCH}\", default empty is used, got empty???${PARAM_1_VALUE}???"
    fi


    INPUT_STRING="the string that has no parameters"
    extract_avp_from_string_or_default ${PARAM_0_TO_SEARCH} "${INPUT_STRING}" "DefAuLtVaLuE_0" '=' PARAM_0_VALUE
    extract_avp_from_string_or_default ${PARAM_1_TO_SEARCH} "${INPUT_STRING}" "DefAuLtVaLuE_1" '=' PARAM_1_VALUE
    assertEquals "\"${INPUT_STRING}\" contains no \"${PARAM_0_TO_SEARCH}\", default is used" ${PARAM_0_VALUE} "DefAuLtVaLuE_0"
    assertEquals "\"${INPUT_STRING}\" contains no \"${PARAM_1_TO_SEARCH}\", default is used" ${PARAM_1_VALUE} "DefAuLtVaLuE_1"

    INPUT_STRING="${PARAM_0_TO_SEARCH}=FOUND_0 ${PARAM_1_TO_SEARCH}=FOUND_1"
    extract_avp_from_string_or_default ${PARAM_0_TO_SEARCH} "${INPUT_STRING}" "" '=' PARAM_0_VALUE
    extract_avp_from_string_or_default ${PARAM_1_TO_SEARCH} "${INPUT_STRING}" "" '=' PARAM_1_VALUE
    assertEquals "\"${INPUT_STRING}\" \"${PARAM_0_TO_SEARCH}\"" ${PARAM_0_VALUE} "FOUND_0"
    assertEquals "\"${INPUT_STRING}\" \"${PARAM_1_TO_SEARCH}\"" ${PARAM_1_VALUE} "FOUND_1"

    INPUT_STRING="${PARAM_1_TO_SEARCH}=FOUND_1 ${PARAM_0_TO_SEARCH}=FOUND_0"
    extract_avp_from_string_or_default ${PARAM_0_TO_SEARCH} "${INPUT_STRING}" "" '=' PARAM_0_VALUE
    extract_avp_from_string_or_default ${PARAM_1_TO_SEARCH} "${INPUT_STRING}" "" '=' PARAM_1_VALUE
    assertEquals "\"${INPUT_STRING}\" \"${PARAM_0_TO_SEARCH}\"" ${PARAM_0_VALUE} "FOUND_0"
    assertEquals "\"${INPUT_STRING}\" \"${PARAM_1_TO_SEARCH}\"" ${PARAM_1_VALUE} "FOUND_1"

    INPUT_STRING="${PARAM_0_TO_SEARCH}=FOUND_0 PARAM_1_TO_SEARCH_NOT_FOUND=FOUND_11111"
    extract_avp_from_string_or_default ${PARAM_0_TO_SEARCH} "${INPUT_STRING}" "" '=' PARAM_0_VALUE
    extract_avp_from_string_or_default ${PARAM_1_TO_SEARCH} "${INPUT_STRING}" "MUST_NOT_BE_FOUND_1" '=' PARAM_1_VALUE
    assertEquals "\"${INPUT_STRING}\" \"${PARAM_0_TO_SEARCH}\"" ${PARAM_0_VALUE} "FOUND_0"
    assertEquals "\"${INPUT_STRING}\" \"${PARAM_1_TO_SEARCH}\" must not be found as a partial match and default must be used" ${PARAM_1_VALUE} "MUST_NOT_BE_FOUND_1"
}

test_add_suffix_if_exist() {
    local SUFFIX_TO_ADD=
    local STR_FOR_ADDING_SUFFIX="my_string"
    local OUTPUT=
    add_suffix_if_exist "${SUFFIX_TO_ADD}" ${STR_FOR_ADDING_SUFFIX} OUTPUT
    assertEquals "Empty suffix must not be attached" ${OUTPUT} ${STR_FOR_ADDING_SUFFIX}

    SUFFIX_TO_ADD="suffix"
    STR_FOR_ADDING_SUFFIX="my_string"
    OUTPUT=
    add_suffix_if_exist "${SUFFIX_TO_ADD}" ${STR_FOR_ADDING_SUFFIX} OUTPUT
    assertEquals "suffix must be attached" ${OUTPUT} ${STR_FOR_ADDING_SUFFIX}_${SUFFIX_TO_ADD}
}


test_wait_until_pipe_exist() {
    PIPE_NAME=/tmp/test_wait_until_pipe_exist_pipe`date +%H%M%S`
    (wait_until_pipe_exist ${PIPE_NAME}) &
    WAIT_PROC_PID=$!
    COUNTER=0
    COUNTER_LIMIT=30
    while [ $COUNTER != ${COUNTER_LIMIT} ]; do
        kill -s 0 ${WAIT_PROC_PID} > /dev/null 2>&1
        assertEquals "Waiting pipe process: ${WAIT_PROC_PID} must stay alive due to no PIPE: ${COUNTER}/${COUNTER_LIMIT}" $? 0
        let COUNTER=${COUNTER}+1
    done
    assertEquals "Waiting pipe process: ${WAIT_PROC_PID} must not be terminated as it's waiting on a PIPE" ${COUNTER} ${COUNTER_LIMIT}

    # create a regular file
    touch ${PIPE_NAME}

    COUNTER=0
    while [ $COUNTER != ${COUNTER_LIMIT} ]; do
        kill -s 0 ${WAIT_PROC_PID} > /dev/null 2>&1
        assertEquals "Waiting pipe process: ${WAIT_PROC_PID} must stay alive because FILE isn't a PIPE: ${COUNTER}/${COUNTER_LIMIT}" $? 0
        let COUNTER=${COUNTER}+1
    done
    assertEquals "Waiting pipe process: ${WAIT_PROC_PID} must not be terminated after a regulate FILE has been created" ${COUNTER} ${COUNTER_LIMIT}

    # create the expected pipe
    rm ${PIPE_NAME}
    mkfifo -m 644 ${PIPE_NAME}

    let COUNTER=0
    while [ $COUNTER != ${COUNTER_LIMIT} ];
    do
        kill -s 0 ${WAIT_PROC_PID} > /dev/null 2>&1
        if [ $? != 0 ]; then
            #echo "Waiting pipe process: ${WAIT_PROC_PID} must stay alive: ${COUNTER}/${COUNTER_LIMIT}";
            let COUNTER=${COUNTER}+1
        else
            break
        fi

    done
    assertNotSame "Waiting pipe process: ${WAIT_PROC_PID} finishes because the pipe created" ${COUNTER} ${COUNTER_LIMIT}
}

test_unblock_query_pipe_by_owner_no_pipe() {
    PIPE_IN="test_fifo"
    unblock_query_pipe_writers_by_owner ${PIPE_IN}
}

test_unblock_query_pipe_by_owner_no_one_stuck() {
    PIPE_IN="test_fifo_no_one_stuck"
    mkfifo -m 644  ${PIPE_IN}
    unblock_query_pipe_writers_by_owner ${PIPE_IN}
}

test_unblock_query_pipe_by_owner_single_request_stuck() {
    PIPE_IN="test_fifo"

    mkfifo -m 644  ${PIPE_IN}
    echo 0 > ${PIPE_IN} &
    PID=$!
    assertEquals `ps -ef | grep ${PID} | grep -v grep | wc -l` 1
    unblock_query_pipe_writers_by_owner ${PIPE_IN}
    assertEquals `ps -ef | grep ${PID} | grep -v grep | wc -l` 0
}

test_unblock_query_pipe_by_owner_multiple_request_stuck() {
    PIPE_IN="test_fifo_multiple_clients"
    mkfifo -m 644  ${PIPE_IN}
    echo 0 > ${PIPE_IN} &
    PID_0=$!
    assertEquals `ps -ef | grep ${PID_0} | grep -v grep | wc -l` 1
    echo 0 > ${PIPE_IN} &
    PID_1=$!
    assertEquals `ps -ef | grep ${PID_1} | grep -v grep | wc -l` 1

    unblock_query_pipe_writers_by_owner ${PIPE_IN}
    assertEquals `ps -ef | grep ${PID_0} | grep -v grep | wc -l` 0
    assertEquals `ps -ef | grep ${PID_1} | grep -v grep | wc -l` 0
}


test_unblock_result_pipe_readers_by_owner_no_pipe() {
    PIPE_OUT="test_fifo"
    unblock_result_pipe_readers_by_owner ${PIPE_OUT}
}

test_unblock_result_pipe_readers_by_owner_no_one_stuck() {
    PIPE_OUT="test_fifo_no_one_stuck"
    mkfifo -m 644  ${PIPE_OUT}
    unblock_result_pipe_readers_by_owner ${PIPE_OUT}
}

test_unblock_result_pipe_readers_by_owner_single_request_stuck() {
    PIPE_OUT="test_fifo"

    mkfifo -m 644  ${PIPE_OUT}
    cat ${PIPE_OUT} &
    PID=$!
    assertEquals `ps -ef | grep ${PID} | grep -v grep | wc -l` 1
    unblock_result_pipe_readers_by_owner ${PIPE_OUT}
    assertEquals `ps -ef | grep ${PID} | grep -v grep | wc -l` 0
}

test_unblock_result_pipe_readers_by_owner_multiple_request_stuck() {
    PIPE_OUT="test_fifo_multiple_clients"
    mkfifo -m 644  ${PIPE_OUT}
    cat ${PIPE_OUT} &
    PID_0=$!
    assertEquals `ps -ef | grep ${PID_0} | grep -v grep | wc -l` 1
    cat ${PIPE_OUT} &
    PID_1=$!
    assertEquals `ps -ef | grep ${PID_1} | grep -v grep | wc -l` 1

    unblock_result_pipe_readers_by_owner ${PIPE_OUT}
    assertEquals `ps -ef | grep ${PID_0} | grep -v grep | wc -l` 0
    assertEquals `ps -ef | grep ${PID_1} | grep -v grep | wc -l` 0

}

test_unblock_readers_of_result_pipe_array_by_owner_multiple_request_stuck() {
    PIPE_OUT_0="test_fifo_multiple_clients_multiple_pipes_0"
    PIPE_OUT_1="test_fifo_multiple_clients_multiple_pipes_1"
    mkfifo -m 644  ${PIPE_OUT_0}
    mkfifo -m 644  ${PIPE_OUT_1}
    cat ${PIPE_OUT_0} &
    PID_0_0=$!
    assertEquals `ps -ef | grep ${PID_0_0} | grep -v grep | wc -l` 1
    cat ${PIPE_OUT_0} &
    PID_0_1=$!
    assertEquals `ps -ef | grep ${PID_0_1} | grep -v grep | wc -l` 1

    cat ${PIPE_OUT_1} &
    PID_1_0=$!
    assertEquals `ps -ef | grep ${PID_1_0} | grep -v grep | wc -l` 1
    cat ${PIPE_OUT_1} &
    PID_1_1=$!
    assertEquals `ps -ef | grep ${PID_1_1} | grep -v grep | wc -l` 1

    unblock_readers_of_result_pipe_array_by_owner "test_fifo_multiple_clients_multiple_pipes_*"
    assertEquals `ps -ef | grep ${PID_0_0} | grep -v grep | wc -l` 0
    assertEquals `ps -ef | grep ${PID_0_1} | grep -v grep | wc -l` 0
    assertEquals `ps -ef | grep ${PID_1_0} | grep -v grep | wc -l` 0
    assertEquals `ps -ef | grep ${PID_1_1} | grep -v grep | wc -l` 0
}

. shunit2
