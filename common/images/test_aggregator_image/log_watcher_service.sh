#!/bin/bash

python3 /package/log_aggregator.py ${1} "^.*\\s.*\\s(.*tester.*)\\[\\d+\\]:.*$" -t=${2} -f pcap > ${3}/result_log_stdout 2> ${3}/result_log_stderr
echo $? > ${3}/result
kill -s SIGTERM ${PPID}
kill -s SIGTERM `pidof envoy`
