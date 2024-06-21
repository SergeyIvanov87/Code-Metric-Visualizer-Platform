#!/bin/bash

source /package/ssh.sh

echo $HOSTNAME
LOG_AGGREGATED_PATH=/logs/syslog-ng
if [ -d ${LOG_AGGREGATED_PATH} ]; then
    rm -rf ${LOG_AGGREGATED_PATH}
fi
mkdir -p ${LOG_AGGREGATED_PATH}

LOG_AGGREGATED_RESULT_PATH=/logs/aggregator/
if [ -d ${LOG_AGGREGATED_RESULT_PATH} ]; then
    rm -rf ${LOG_AGGREGATED_RESULT_PATH}
fi
mkdir -p ${LOG_AGGREGATED_RESULT_PATH}

echo "Wait until syslog-ng SSH server started"
wait_for_ssh "root" "${DOWNSTREAM_SYSLOG_HOSTNAME}" "${DOWNSTREAM_SSH_SECRET}"
execute_ssh_cmd "root" "${DOWNSTREAM_SYSLOG_HOSTNAME}" "${DOWNSTREAM_SSH_SECRET}" "while syslog-ng-ctl healthcheck -c /config/syslog-ng.ctl && [[ $? != 0 ]]; do echo \"waiting for syslog-ng running...\" && sleep 1; done"

termination_handler(){
    trap - QUIT TERM EXIT

    RET=`cat ${LOG_AGGREGATED_RESULT_PATH}/result`
    echo "Test aggregator result: ${RET}. Full log can be found: "
    echo "- ${LOG_AGGREGATED_RESULT_PATH}/result_log_out"
    echo "- ${LOG_AGGREGATED_RESULT_PATH}/result_log_err"
    echo "- ${LOG_AGGREGATED_PATH}/tester.log"
    exit ${RET}
}

echo "Setup signal handlers"
trap 'termination_handler' QUIT TERM EXIT

# capture traffic from syslog-ng port | compel line ending \r\n | turn off stdoutput bufferization | decode from hex and redirect into file
tshark -f "tcp port ${UPSTREAM_AGGREGATOR_TCP_PORT}" -i any -l -T fields -e tcp.payload | xargs -I{} echo "{}0d0a" | stdbuf -i0 -o0 -e0  xxd -r -p - > ${LOG_AGGREGATED_PATH}/tester.log  &
/package/log_watcher_service.sh ${LOG_AGGREGATED_PATH} ${WAIT_MSEC_UNTIL_FINISH} ${LOG_AGGREGATED_RESULT_PATH} &


# clear previously gathered log files to start over
#rm -f /logs/*

# bootstrap envoy.yaml
sed -i "s/UPSTREAM_AGGREGATOR_TCP_PORT/${UPSTREAM_AGGREGATOR_TCP_PORT}/" /etc/envoy/envoy.yaml
sed -i "s/DOWNSTREAM_SYSLOG_TCP_PORT/${DOWNSTREAM_SYSLOG_TCP_PORT}/" /etc/envoy/envoy.yaml
sed -i "s/DOWNSTREAM_SYSLOG_HOSTNAME/${DOWNSTREAM_SYSLOG_HOSTNAME}/" /etc/envoy/envoy.yaml

# docker inspect results used here [ENTRYPOINT + CMD]
/docker-entrypoint.sh envoy -c /etc/envoy/envoy.yaml

RET=`cat ${LOG_AGGREGATED_PATH}/result`
echo "Test aggregator result: ${RET}.Full log can be found: ${LOG_AGGREGATED_PATH}/result_log"
exit ${RET}
