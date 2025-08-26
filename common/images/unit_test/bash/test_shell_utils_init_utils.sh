#!/bin/bash

test_suite_filename=${0}

source /tests/shell_utils/init_utils.sh

test_gracefull_shutdown() {
    declare -A SERVICE_WATCH_PIDS_TO_STOP

    process_name_0="sleep infinity &"
    eval $process_name_0
    SERVICE_WATCH_PIDS_TO_STOP[${process_name_0}]=$!

    tmp_fifo_name="/tmp/tests_sandbox_`date +%H%M%S`"
    process_name_1="mkfifo -m 644 ${tmp_fifo_name} && cat ${tmp_fifo_name} &"
    eval $process_name_1
    SERVICE_WATCH_PIDS_TO_STOP[${process_name_1}]=$!

    (tail -f /dev/null) &
    API_MANAGEMENT_PID=$?

    assertEquals `ps -ef | grep ${SERVICE_WATCH_PIDS_TO_STOP[${process_name_0}]} | grep -v grep | wc -l` 1
    assertEquals `ps -ef | grep ${SERVICE_WATCH_PIDS_TO_STOP[${process_name_1}]} | grep -v grep | wc -l` 1
    assertEquals `ps -ef | grep ${API_MANAGEMENT_PID} | grep -v grep | wc -l` 1

    gracefull_shutdown SERVICE_WATCH_PIDS_TO_STOP API_MANAGEMENT_PID

    assertEquals `ps -ef | grep ${SERVICE_WATCH_PIDS_TO_STOP[${process_name_0}]} | grep -v grep | wc -l` 1
    assertEquals `ps -ef | grep ${SERVICE_WATCH_PIDS_TO_STOP[${process_name_1}]} | grep -v grep | wc -l` 1
    assertEquals `ps -ef | grep ${API_MANAGEMENT_PID} | grep -v grep | wc -l` 1
}


test_gracefull_shutdown_bunch() {
    declare -A SERVICE_WATCH_PIDS_TO_STOP
    declare -A API_MANAGEMENT_PID

    process_name_0="sleep infinity &"
    eval $process_name_0
    SERVICE_WATCH_PIDS_TO_STOP[${process_name_0}]=$!

    tmp_fifo_name="/tmp/tests_sandbox_`date +%H%M%S`"
    process_name_1="mkfifo -m 644 ${tmp_fifo_name} && cat ${tmp_fifo_name} &"
    eval $process_name_1
    SERVICE_WATCH_PIDS_TO_STOP[${process_name_1}]=$!

    process_management_name_0="tail -f /dev/null &"
    eval $process_management_name_0
    API_MANAGEMENT_PID[${process_management_name_0}]=$?

    process_management_name_1="sleep infinity &"
    eval $process_management_name_1
    API_MANAGEMENT_PID[${process_management_name_1}]=$?

    assertEquals `ps -ef | grep ${SERVICE_WATCH_PIDS_TO_STOP[${process_name_0}]} | grep -v grep | wc -l` 1
    assertEquals `ps -ef | grep ${SERVICE_WATCH_PIDS_TO_STOP[${process_name_1}]} | grep -v grep | wc -l` 1
    assertEquals `ps -ef | grep ${API_MANAGEMENT_PID[${process_management_name_0}]} | grep -v grep | wc -l` 1
    assertEquals `ps -ef | grep ${API_MANAGEMENT_PID[${process_management_name_1}]} | grep -v grep | wc -l` 1

    gracefull_shutdown_bunch SERVICE_WATCH_PIDS_TO_STOP API_MANAGEMENT_PID

    assertEquals `ps -ef | grep ${SERVICE_WATCH_PIDS_TO_STOP[${process_name_0}]} | grep -v grep | wc -l` 0
    assertEquals `ps -ef | grep ${SERVICE_WATCH_PIDS_TO_STOP[${process_name_1}]} | grep -v grep | wc -l` 0
    assertEquals `ps -ef | grep ${API_MANAGEMENT_PID[${process_management_name_0}]} | grep -v grep | wc -l` 0
    assertEquals `ps -ef | grep ${API_MANAGEMENT_PID[${process_management_name_1}]} | grep -v grep | wc -l` 0
}
