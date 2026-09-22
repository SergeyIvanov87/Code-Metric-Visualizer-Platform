#!/bin/bash
set -u

TAP_PATH=/logs/subscriber/taps
DECODED_LOG_PATH=/logs/subscriber/streams
AGGREGATED_CONNECTIONS_LOG_PATH=/logs/subscriber/aggregated_connection
RESULT_PATH=/logs/subscriber/status
rm -rf "${TAP_PATH}" "${DECODED_LOG_PATH}" "${RESULT_PATH}" "${AGGREGATED_CONNECTIONS_LOG_PATH}"
mkdir -p "${TAP_PATH}" "${DECODED_LOG_PATH}" "${RESULT_PATH}" "${AGGREGATED_CONNECTIONS_LOG_PATH}"

subscriber_options=()
if [[ "${RETAIN_RAW_TAPS:-false}" == "true" ]]; then
  subscriber_options+=(--retain-raw-taps)
fi

max_wait_msec=${MAX_WAIT_MSEC_UNTIL_FINISH:-}
if [[ -n "${max_wait_msec}" && ! "${max_wait_msec}" =~ ^[1-9][0-9]*$ ]]; then
  echo "MAX_WAIT_MSEC_UNTIL_FINISH must be empty or a positive integer" >&2
  exit 2
fi

first_tap_wait_msec=${WAIT_FOR_FIRST_TAP_BEFORE_FINISH_MSEC:-0}
next_tap_wait_msec=${WAIT_FOR_NEXT_TAP_BEFORE_FINISH_MSEC:-0}
kafka_delivery_timeout_seconds=${KAFKA_DELIVERY_TIMEOUT_SECONDS:-120}
for wait_setting in \
  "first tap wait:${first_tap_wait_msec}" \
  "next tap wait:${next_tap_wait_msec}" \
  "Kafka delivery timeout:${kafka_delivery_timeout_seconds}"; do
  setting_name=${wait_setting%%:*}
  setting_value=${wait_setting#*:}
  if [[ ! "${setting_value}" =~ ^[0-9]+$ ]]; then
    echo "${setting_name} must be a non-negative integer" >&2
    exit 2
  fi
done

# Give every capture wait plus the final Kafka drain an opportunity to finish,
# but always retain a non-zero deadline before escalating SIGTERM to SIGKILL.
shutdown_timeout_msec=$((
  first_tap_wait_msec
  + next_tap_wait_msec
  + kafka_delivery_timeout_seconds * 1000
))
if (( shutdown_timeout_msec == 0 )); then
  shutdown_timeout_msec=1
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
  --kafka-delivery-timeout-seconds "${kafka_delivery_timeout_seconds}" \
  --capture-id "${CAPTURE_ID}" \
  "${subscriber_options[@]}" \
  > "${RESULT_PATH}/subscriber_stdout" \
  2> "${RESULT_PATH}/subscriber_stderr" &
subscriber_pid=$!

lifecycle_watchdog_pid=
if [[ -n "${max_wait_msec}" ]]; then
  /package/lifecycle_watchdog.sh \
    "${subscriber_pid}" "${max_wait_msec}" "${shutdown_timeout_msec}" &
  lifecycle_watchdog_pid=$!
fi

shutdown_watchdog_pid=
forward_shutdown() {
  if [[ -z "${shutdown_watchdog_pid}" ]]; then
    if [[ -n "${lifecycle_watchdog_pid}" ]]; then
      kill "${lifecycle_watchdog_pid}" 2>/dev/null || true
    fi
    /package/lifecycle_watchdog.sh \
      "${subscriber_pid}" 0 "${shutdown_timeout_msec}" &
    shutdown_watchdog_pid=$!
  fi
}
trap forward_shutdown HUP INT QUIT TERM

wait "${subscriber_pid}"
subscriber_result=$?
# A signal interrupts bash's wait. The shutdown watchdog bounds this second
# wait and sends SIGKILL if graceful finalization does not complete in time.
if kill -0 "${subscriber_pid}" 2>/dev/null; then
  wait "${subscriber_pid}"
  subscriber_result=$?
fi

aggregation_error_file="${RESULT_PATH}/connection_aggregation_stderr"
aggregation_result_file="${RESULT_PATH}/connection_aggregation_result"
if python3 /package/aggregate_connection_logs.py \
    "${DECODED_LOG_PATH}" "${AGGREGATED_CONNECTIONS_LOG_PATH}" \
    2> "${aggregation_error_file}"; then
    rm -f "${aggregation_error_file}"
else
    aggregation_error=$(cat "${aggregation_error_file}")
    # Discard any producer files published before the failure. Besides
    # making partial output unmistakable, this can recover enough volume
    # space to persist the infrastructure-failure result.
    rm -f "${AGGREGATED_CONNECTIONS_LOG_PATH}"/* "${aggregation_error_file}"
    {
        echo "Per-producer connection log aggregation failed"
        printf '%s\n' "${aggregation_error}"
    } >> "${RESULT_PATH}/subscriber_stdout"
    : >> "${RESULT_PATH}/subscriber_stderr"
    echo 255 > "${aggregation_result_file}"
fi

trap - HUP INT QUIT TERM
for watchdog_pid in "${lifecycle_watchdog_pid}" "${shutdown_watchdog_pid}"; do
  if [[ -n "${watchdog_pid}" ]]; then
    kill "${watchdog_pid}" 2>/dev/null || true
    wait "${watchdog_pid}" 2>/dev/null || true
  fi
done

if (( subscriber_result != 0 && subscriber_result != 10 )); then
  python3 /package/publish_capture_failure.py \
    --brokers "${KAFKA_BOOTSTRAP_SERVERS}" \
    --topic "${KAFKA_TOPIC}" \
    --capture-id "${CAPTURE_ID}" \
    --error-file "${RESULT_PATH}/subscriber_stderr" || true
  cat "${RESULT_PATH}/subscriber_stderr" >&2
fi
exit "${subscriber_result}"
