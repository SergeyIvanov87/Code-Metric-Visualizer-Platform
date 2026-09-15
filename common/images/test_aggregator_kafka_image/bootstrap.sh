#!/bin/bash
set -u
DECODED_LOG_PATH=/logs/syslog-streams
RESULT_PATH=/logs/aggregator
rm -rf "${DECODED_LOG_PATH}" "${RESULT_PATH}"
mkdir -p "${DECODED_LOG_PATH}" "${RESULT_PATH}"
python3 /package/kafka_test_aggregator.py \
  --brokers "${KAFKA_BOOTSTRAP_SERVERS}" \
  --topic "${KAFKA_TOPIC}" \
  --group-id "${KAFKA_CONSUMER_GROUP}" \
  --capture-id "${CAPTURE_ID}" \
  --output-directory "${DECODED_LOG_PATH}" \
  --result-directory "${RESULT_PATH}" \
  --timeout-seconds "${MAX_WAIT_SECONDS:-900}" \
  --ready-file "${RESULT_PATH}/consumer_ready"
