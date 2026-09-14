#!/bin/bash

source /package/ssh.sh

echo "${HOSTNAME}"

TAP_PATH=/logs/taps
DECODED_LOG_PATH=/logs/syslog-streams
LOG_AGGREGATED_RESULT_PATH=/logs/aggregator

for path in "${TAP_PATH}" "${DECODED_LOG_PATH}" "${LOG_AGGREGATED_RESULT_PATH}"; do
    if [[ -d "${path}" ]]; then
        rm -rf "${path}"
    fi
    mkdir -p "${path}"
done

# /logs is a runtime volume, so the image-layer permissions from the
# Dockerfile are hidden when the container starts. The Envoy entrypoint drops
# privileges to the `envoy` user; grant that user access to the only directory
# it needs to write while leaving the watcher-owned output directories alone.
chown envoy:envoy "${TAP_PATH}"
chmod 0750 "${TAP_PATH}"

echo "Remove all SSH stored keys to prevent 'man-in-the-middle' complaint, as host identities may change in our virtual network"
rm -f /root/.ssh/known_hosts

echo "Wait until syslog-ng SSH server started"
wait_for_ssh "root" "${DOWNSTREAM_SYSLOG_HOSTNAME}" "${DOWNSTREAM_SSH_SECRET}"
execute_ssh_cmd "root" "${DOWNSTREAM_SYSLOG_HOSTNAME}" "${DOWNSTREAM_SSH_SECRET}" "while syslog-ng-ctl healthcheck -c /config/syslog-ng.ctl && [[ \$? != 0 ]]; do echo \"waiting for syslog-ng running...\" && sleep 1; done"

termination_handler() {
    trap - QUIT TERM EXIT

    if [[ -n "${tap_watcher_pid:-}" ]] && kill -0 "${tap_watcher_pid}" 2>/dev/null; then
        kill "${tap_watcher_pid}" 2>/dev/null
    fi
    if [[ -n "${envoy_pid:-}" ]] && kill -0 "${envoy_pid}" 2>/dev/null; then
        kill "${envoy_pid}" 2>/dev/null
    fi

    if [[ -f "${LOG_AGGREGATED_RESULT_PATH}/result" ]]; then
        result=$(cat "${LOG_AGGREGATED_RESULT_PATH}/result")
    else
        result=255
        echo "The tap watcher stopped without producing a result" \
            > "${LOG_AGGREGATED_RESULT_PATH}/result_log_stderr"
    fi

    echo "Test Suites execution result: ${result}. Full log can be found:"
    echo "- ${LOG_AGGREGATED_RESULT_PATH}/result_log_stdout"
    echo "- ${LOG_AGGREGATED_RESULT_PATH}/result_log_stderr"
    echo "- raw Envoy taps: ${TAP_PATH}"
    echo "- reconstructed syslog streams: ${DECODED_LOG_PATH}"

    if [[ "${result}" != 0 ]]; then
        echo "================================================================="
        echo "| Reconstructed traffic designated for syslog-ng                 |"
        echo "================================================================="
        for log_file in "${DECODED_LOG_PATH}"/*.log; do
            if [[ -f "${log_file}" ]]; then
                echo "--- ${log_file}"
                cat "${log_file}"
            fi
        done
        echo "================================================================="
        echo "| Aggregation/decoding errors                                    |"
        echo "================================================================="
        if [[ -f "${LOG_AGGREGATED_RESULT_PATH}/result_log_stderr" ]]; then
            cat "${LOG_AGGREGATED_RESULT_PATH}/result_log_stderr"
        fi
        echo "================================================================="
    fi
    exit "${result}"
}

echo "Setup signal handlers"
trap termination_handler QUIT TERM EXIT

# Bootstrap the port/address placeholders before starting Envoy.
sed -i "s/UPSTREAM_AGGREGATOR_TCP_PORT/${UPSTREAM_AGGREGATOR_TCP_PORT}/" /etc/envoy/envoy.yaml
sed -i "s/DOWNSTREAM_SYSLOG_TCP_PORT/${DOWNSTREAM_SYSLOG_TCP_PORT}/" /etc/envoy/envoy.yaml
sed -i "s/DOWNSTREAM_SYSLOG_HOSTNAME/${DOWNSTREAM_SYSLOG_HOSTNAME}/" /etc/envoy/envoy.yaml

# The watcher is ready before Envoy accepts its first connection. It resets its
# inactivity timer on tap writes and decodes a connection only on CLOSE_WRITE.
/package/tap_watcher_service.sh \
    "${TAP_PATH}" \
    "${DECODED_LOG_PATH}" \
    "${WAIT_MSEC_UNTIL_FINISH}" \
    "${LOG_AGGREGATED_RESULT_PATH}" \
    "${MAX_WAIT_MSEC_UNTIL_FINISH:-900000}" &
tap_watcher_pid=$!

watcher_start_second=$SECONDS
while [[ ! -f "${LOG_AGGREGATED_RESULT_PATH}/watcher_ready" ]]; do
    if ! kill -0 "${tap_watcher_pid}" 2>/dev/null || (( SECONDS - watcher_start_second >= 10 )); then
        echo "The Envoy tap file watcher did not become ready" \
            > "${LOG_AGGREGATED_RESULT_PATH}/result_log_stderr"
        : > "${LOG_AGGREGATED_RESULT_PATH}/result_log_stdout"
        echo 255 > "${LOG_AGGREGATED_RESULT_PATH}/result"
        exit 255
    fi
    sleep 1
done

/docker-entrypoint.sh envoy -c /etc/envoy/envoy.yaml &
envoy_pid=$!

capture_stop_request="${LOG_AGGREGATED_RESULT_PATH}/capture_stop_requested"
envoy_stop_sent=0

while kill -0 "${tap_watcher_pid}" 2>/dev/null; do
    if [[ -f "${capture_stop_request}" ]]; then
        if (( envoy_stop_sent == 0 )) && kill -0 "${envoy_pid}" 2>/dev/null; then
            kill "${envoy_pid}" 2>/dev/null
            envoy_stop_sent=1
        fi
    elif ! kill -0 "${envoy_pid}" 2>/dev/null; then
        echo "Envoy exited before log aggregation completed" \
            > "${LOG_AGGREGATED_RESULT_PATH}/result_log_stderr"
        : > "${LOG_AGGREGATED_RESULT_PATH}/result_log_stdout"
        echo 255 > "${LOG_AGGREGATED_RESULT_PATH}/result"
        kill "${tap_watcher_pid}" 2>/dev/null
        break
    fi
    sleep 1
done

wait "${tap_watcher_pid}" 2>/dev/null
result=$(cat "${LOG_AGGREGATED_RESULT_PATH}/result")

if kill -0 "${envoy_pid}" 2>/dev/null; then
    kill "${envoy_pid}" 2>/dev/null
fi
wait "${envoy_pid}" 2>/dev/null

exit "${result}"
