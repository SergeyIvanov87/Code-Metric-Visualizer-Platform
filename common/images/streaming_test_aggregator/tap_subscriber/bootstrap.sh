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

max_wait_msec=${MAX_WAIT_MSEC_UNTIL_FINISH:-}
if [[ -n "${max_wait_msec}" && ! "${max_wait_msec}" =~ ^[1-9][0-9]*$ ]]; then
  echo "MAX_WAIT_MSEC_UNTIL_FINISH must be empty or a positive integer" >&2
  exit 2
fi

python3 /package/tap_subscriber.py \
  --admin-url "http://${ENVOY_ADMIN_HOST}:${ENVOY_ADMIN_PORT}" \
  --config-id "${ENVOY_TAP_CONFIG_ID}" \
  --tap-directory "${TAP_PATH}" \
  --decoded-directory "${DECODED_LOG_PATH}" \
  --wait-for-next-tap-before-finish-msec "${WAIT_FOR_NEXT_TAP_BEFORE_FINISH_MSEC:-}" \
  --wait-for-first-tap-before-finish-msec "${WAIT_FOR_FIRST_TAP_BEFORE_FINISH_MSEC:-}" \
  --max-buffered-rx-bytes "${MAX_BUFFERED_RX_BYTES:-16777216}" \
  --ready-file "${RESULT_PATH}/subscriber_ready" \
  --kafka-brokers "${KAFKA_BOOTSTRAP_SERVERS}" \
  --kafka-topic "${KAFKA_TOPIC}" \
  --kafka-delivery-timeout-seconds "${KAFKA_DELIVERY_TIMEOUT_SECONDS:-120}" \
  --capture-id "${CAPTURE_ID}" \
  "${subscriber_options[@]}" \
  > "${RESULT_PATH}/subscriber_stdout" \
  2> "${RESULT_PATH}/subscriber_stderr" &
subscriber_pid=$!

watchdog_pid=
if [[ -n "${max_wait_msec}" ]]; then
  /package/lifecycle_watchdog.sh "${subscriber_pid}" "${max_wait_msec}" &
  watchdog_pid=$!
fi

forward_shutdown() {
  kill -TERM "${subscriber_pid}" 2>/dev/null || true
}
trap forward_shutdown HUP INT QUIT TERM

wait "${subscriber_pid}"
subscriber_result=$?
# A signal interrupts bash's wait before the subscriber has completed its
# graceful Kafka drain. Wait again rather than letting PID 1 exit early.
if kill -0 "${subscriber_pid}" 2>/dev/null; then
  wait "${subscriber_pid}"
  subscriber_result=$?
fi
trap - HUP INT QUIT TERM
if [[ -n "${watchdog_pid}" ]]; then
  kill "${watchdog_pid}" 2>/dev/null || true
  wait "${watchdog_pid}" 2>/dev/null || true
fi

if (( subscriber_result != 0 && subscriber_result != 10 )); then
  python3 /package/publish_capture_failure.py \
    --brokers "${KAFKA_BOOTSTRAP_SERVERS}" \
    --topic "${KAFKA_TOPIC}" \
    --capture-id "${CAPTURE_ID}" \
    --error-file "${RESULT_PATH}/subscriber_stderr" || true
  cat "${RESULT_PATH}/subscriber_stderr" >&2
fi
exit "${subscriber_result}"
