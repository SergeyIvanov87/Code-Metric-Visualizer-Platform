#!/bin/bash
set -u

TAP_PATH=/logs/taps
DECODED_LOG_PATH=/logs/syslog-streams
RESULT_PATH=/logs/aggregator
rm -rf "${TAP_PATH}" "${DECODED_LOG_PATH}" "${RESULT_PATH}"
mkdir -p "${TAP_PATH}" "${DECODED_LOG_PATH}" "${RESULT_PATH}"

subscriber_options=()
if [[ "${RETAIN_RAW_TAPS:-false}" == "true" ]]; then
  subscriber_options+=(--retain-raw-taps)
fi

python3 /package/streaming_admin_tap.py \
  --admin-url "http://${ENVOY_ADMIN_HOST}:${ENVOY_ADMIN_PORT}" \
  --config-id "${ENVOY_TAP_CONFIG_ID}" \
  --tap-directory "${TAP_PATH}" \
  --decoded-directory "${DECODED_LOG_PATH}" \
  --quiet-msec "${WAIT_MSEC_UNTIL_FINISH}" \
  --max-wait-msec "${MAX_WAIT_MSEC_UNTIL_FINISH}" \
  --max-buffered-rx-bytes "${MAX_BUFFERED_RX_BYTES:-16777216}" \
  --ready-file "${RESULT_PATH}/subscriber_ready" \
  "${subscriber_options[@]}" \
  > "${RESULT_PATH}/subscriber_stdout" \
  2> "${RESULT_PATH}/subscriber_stderr"
subscriber_result=$?

if (( subscriber_result == 0 )); then
  /package/log_watcher_service.sh "${DECODED_LOG_PATH}" 1 "${RESULT_PATH}"
else
  cp "${RESULT_PATH}/subscriber_stderr" "${RESULT_PATH}/result_log_stderr"
  : > "${RESULT_PATH}/result_log_stdout"
  echo 255 > "${RESULT_PATH}/result"
fi

result=$(cat "${RESULT_PATH}/result")
echo "Test Suites execution result: ${result}."
echo "Optional raw Envoy taps: ${TAP_PATH}"
echo "Reconstructed syslog streams: ${DECODED_LOG_PATH}"
if [[ "${result}" != 0 ]]; then
  cat "${RESULT_PATH}/result_log_stderr" >&2
fi
exit "${result}"
