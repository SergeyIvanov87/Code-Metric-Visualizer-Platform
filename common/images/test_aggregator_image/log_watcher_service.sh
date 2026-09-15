#!/bin/bash

log_path=$1
timeout_msec=$2
result_path=$3

python3 /package/log_aggregator.py "${log_path}" "^.*\\s.*\\s(.*tester.*)\\[\\d+\\]:.*$" -t="${timeout_msec}" -f pcap \
    > "${result_path}/result_log_stdout" \
    2> "${result_path}/result_log_stderr"
echo $? > "${result_path}/result"
