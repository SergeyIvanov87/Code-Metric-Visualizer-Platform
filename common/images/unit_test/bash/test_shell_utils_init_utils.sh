#!/bin/bash

test_suite_filename=${0}

source /tests/shell_utils/init_utils.sh

################################################################################
test_gracefull_shutdown() {
    declare -A SERVICE_WATCH_PIDS_TO_STOP

    process_name_0="echo 'test_gracefull_shutdown starts' > /dev/null && sleep infinity &"
    eval $process_name_0
    SERVICE_WATCH_PIDS_TO_STOP[${process_name_0}]=$!

    tmp_fifo_name="/tmp/tests_sandbox_pipe_`date +%H%M%S`"
    process_name_1="mkfifo -m 644 ${tmp_fifo_name} && cat ${tmp_fifo_name} && rm -f ${tmp_fifo_name}&"
    eval $process_name_1
    SERVICE_WATCH_PIDS_TO_STOP[${process_name_1}]=$!

    (tail -f /dev/null) &
    API_MANAGEMENT_PID=$!

    assertEquals "process_name_0 must have 1 instance" `ps -ef | grep ${SERVICE_WATCH_PIDS_TO_STOP[${process_name_0}]} | grep -v grep | wc -l` 1
    assertEquals "process_name_1 must have 1 instance" `ps -ef | grep ${SERVICE_WATCH_PIDS_TO_STOP[${process_name_1}]} | grep -v grep | wc -l` 1
    assertEquals "API_MANAGEMENT_PID must have 1 instance" `ps -ef | grep ${API_MANAGEMENT_PID} | grep -v grep | wc -l` 1

    gracefull_shutdown SERVICE_WATCH_PIDS_TO_STOP ${API_MANAGEMENT_PID}

    assertEquals `ps -ef | grep ${SERVICE_WATCH_PIDS_TO_STOP[${process_name_0}]} | grep -v grep | wc -l` 0
    assertEquals `ps -ef | grep ${SERVICE_WATCH_PIDS_TO_STOP[${process_name_1}]} | grep -v grep | wc -l` 0
    assertEquals `ps -ef | grep ${API_MANAGEMENT_PID} | grep -v grep | wc -l` 0
}


test_gracefull_shutdown_bunch() {
    declare -A SERVICE_WATCH_PIDS_TO_STOP
    declare -A API_MANAGEMENT_PID

    process_name_0="echo 'test_gracefull_shutdown_bunch process_name_0' && sleep infinity &"
    eval $process_name_0
    SERVICE_WATCH_PIDS_TO_STOP[${process_name_0}]=$!

    tmp_fifo_name="/tmp/tests_sandbox_pipe_bunch_`date +%H%M%S`"
    process_name_1="mkfifo -m 644 ${tmp_fifo_name} && cat ${tmp_fifo_name} &"
    eval $process_name_1
    SERVICE_WATCH_PIDS_TO_STOP[${process_name_1}]=$!

    process_management_name_0="tail -f /dev/null &"
    eval $process_management_name_0
    API_MANAGEMENT_PID[${process_management_name_0}]=$!

    process_management_name_1="echo 'test_gracefull_shutdown_bunch process_management_name_1' && sleep infinity &"
    eval $process_management_name_1
    API_MANAGEMENT_PID[${process_management_name_1}]=$!

    assertEquals "process_name_0 must have 1 instance" `ps -ef | grep ${SERVICE_WATCH_PIDS_TO_STOP[${process_name_0}]} | grep -v grep | wc -l` 1
    assertEquals "process_name_1 must have 1 instance" `ps -ef | grep ${SERVICE_WATCH_PIDS_TO_STOP[${process_name_1}]} | grep -v grep | wc -l` 1
    assertEquals "API_MANAGEMENT_PID must have 1 instance of process_management_name_0" `ps -ef | grep ${API_MANAGEMENT_PID[${process_management_name_0}]} | grep -v grep | wc -l` 1
    assertEquals "API_MANAGEMENT_PID must have 1 instance of process_management_name_1" `ps -ef | grep ${API_MANAGEMENT_PID[${process_management_name_1}]} | grep -v grep | wc -l` 1

    gracefull_shutdown_bunch SERVICE_WATCH_PIDS_TO_STOP API_MANAGEMENT_PID

    assertEquals `ps -ef | grep ${SERVICE_WATCH_PIDS_TO_STOP[${process_name_0}]} | grep -v grep | wc -l` 0
    assertEquals `ps -ef | grep ${SERVICE_WATCH_PIDS_TO_STOP[${process_name_1}]} | grep -v grep | wc -l` 0
    assertEquals `ps -ef | grep ${API_MANAGEMENT_PID[${process_management_name_0}]} | grep -v grep | wc -l` 0
    assertEquals `ps -ef | grep ${API_MANAGEMENT_PID[${process_management_name_1}]} | grep -v grep | wc -l` 0
}

################################################################################
test_wait_until_pipe_appear_timeout() {
    local pipe="/tmp/test_wait_until_pipe_appear`date +%H%M%S`"
    local timeout=10
    wait_until_pipe_appear ${pipe} ${timeout} 1 WAIT_RESULT
    assertEquals ${WAIT_RESULT} 255
}

test_wait_until_pipe_appear_success() {
    local pipe="/tmp/test_wait_until_pipe_appear`date +%H%M%S`"
    local timeout=10
    (sleep 2 && mkfifo -m 644 ${pipe}) &
    wait_until_pipe_appear ${pipe} ${timeout} 1 WAIT_RESULT
    rm -f ${pipe}
    assertEquals ${WAIT_RESULT} 0
}

################################################################################
test_send_own_ka_watchdog_query() {
    local query_pipe="/tmp/test_send_own_ka_watchdog_query_`date +%H%M%S`"
    local session_id="MySession_`date +%H%M%S`"
    local query_timeout_sec=15

    # no pipe
    send_ka_watchdog_query ${query_pipe} ${session_id} ".*"  ${query_timeout_sec}
    assertEquals $? 255

    # query hangs
    (mkfifo -m 644 ${query_pipe} && echo 0 > ${query_pipe}) &
    local WAIT_PID=$!
    assertEquals `ps -ef | grep ${WAIT_PID} | grep -v grep | wc -l` 1
    send_ka_watchdog_query ${query_pipe} ${session_id} ".*"  ${query_timeout_sec}
    local RET=$?
    rm -f ${query_pipe}
    assertEquals ${RET} 255
    assertEquals `ps -ef | grep ${WAIT_PID} | grep -v grep | wc -l` 0

    # success case
    (mkfifo -m 644 ${query_pipe} && echo 0 > ${query_pipe}) &
    WAIT_PID=$!
    assertEquals `ps -ef | grep ${WAIT_PID} | grep -v grep | wc -l` 1

    (sleep 5 && cat ${query_pipe} > /dev/null 2>&1) &
    local SERVICE_PID=$!
    assertEquals `ps -ef | grep ${SERVICE_PID} | grep -v grep | wc -l` 1

    send_ka_watchdog_query ${query_pipe} ${session_id} ".*"  ${query_timeout_sec}
    local RET=$?
    rm -f ${query_pipe}

    assertEquals ${RET} 0
    assertEquals `ps -ef | grep ${WAIT_PID} | grep -v grep | wc -l` 0
    assertEquals `ps -ef | grep ${SERVICE_PID} | grep -v grep | wc -l` 0
}

################################################################################
test_receive_own_ka_watchdog_query() {
    local result_pipe="/tmp/test_receive_own_ka_watchdog_query_`date +%H%M%S`"
    local session_id="MySession_`date +%H%M%S`"
    local query_timeout_sec=15

    # no pipe
    receive_ka_watchdog_query ${result_pipe} ${query_timeout_sec} MISSING_API_QUERIES
    assertEquals $? 255

    # no response
    mkfifo -m 644 ${result_pipe}
    receive_ka_watchdog_query ${result_pipe} ${query_timeout_sec} MISSING_API_QUERIES
    local RET=$?
    rm -f ${result_pipe}
    assertEquals ${RET} 255

    #  response
    (mkfifo -m 644 ${result_pipe} && sleep 5 && echo "ABRACADABRA" > ${result_pipe}) &
    WAIT_PID=$!
    assertEquals `ps -ef | grep ${WAIT_PID} | grep -v grep | wc -l` 1
    receive_ka_watchdog_query ${result_pipe} ${query_timeout_sec} MISSING_API_QUERIES
    local RET=$?
    rm -f ${result_pipe}
    assertEquals ${RET} 0
    assertEquals ${MISSING_API_QUERIES} "ABRACADABRA"
}

################################################################################
. shunit2
