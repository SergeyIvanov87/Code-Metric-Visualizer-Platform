#!/bin/bash
set -u

TAP_PATH=/logs/subscriber/taps
DECODED_LOG_PATH=/logs/subscriber/streams
RESULT_PATH=/logs/subscriber/status
rm -rf "${TAP_PATH}" "${DECODED_LOG_PATH}" "${RESULT_PATH}"
mkdir -p "${TAP_PATH}" "${DECODED_LOG_PATH}" "${RESULT_PATH}"

subscriber_options=()
if [[ "${RETAIN_RAW_TAPS:-false}" == "true" ]]; then
  subscriber_options+=(--retain-raw-taps)
fi

python3 /package/tap_subscriber.py \
  --admin-url "http://${ENVOY_ADMIN_HOST}:${ENVOY_ADMIN_PORT}" \
  --config-id "${ENVOY_TAP_CONFIG_ID}" \
  --tap-directory "${TAP_PATH}" \
  --decoded-directory "${DECODED_LOG_PATH}" \
  --quiet-msec "${WAIT_MSEC_UNTIL_FINISH}" \
  --wait-before-start-msec "${WAIT_MSEC_BEFORE_START}" \
  --max-wait-msec "${MAX_WAIT_MSEC_UNTIL_FINISH}" \
  --max-buffered-rx-bytes "${MAX_BUFFERED_RX_BYTES:-16777216}" \
  --ready-file "${RESULT_PATH}/subscriber_ready" \
  --kafka-brokers "${KAFKA_BOOTSTRAP_SERVERS}" \
  --kafka-topic "${KAFKA_TOPIC}" \
  --kafka-delivery-timeout-seconds "${KAFKA_DELIVERY_TIMEOUT_SECONDS:-120}" \
  --capture-id "${CAPTURE_ID}" \
  "${subscriber_options[@]}" \
  > "${RESULT_PATH}/subscriber_stdout" \
  2> "${RESULT_PATH}/subscriber_stderr"
subscriber_result=$?

if (( subscriber_result != 0 && subscriber_result != 10 )); then
  python3 /package/publish_capture_failure.py \
    --brokers "${KAFKA_BOOTSTRAP_SERVERS}" \
    --topic "${KAFKA_TOPIC}" \
    --capture-id "${CAPTURE_ID}" \
    --error-file "${RESULT_PATH}/subscriber_stderr" || true
  cat "${RESULT_PATH}/subscriber_stderr" >&2
fi
exit "${subscriber_result}"
