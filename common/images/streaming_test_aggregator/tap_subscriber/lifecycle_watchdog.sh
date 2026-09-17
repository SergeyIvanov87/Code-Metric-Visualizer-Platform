#!/bin/bash
set -eu

subscriber_pid=$1
max_wait_msec=$2
shutdown_timeout_msec=$3

sleep "$((max_wait_msec / 1000)).$(printf '%03d' "$((max_wait_msec % 1000))")"
kill -TERM "${subscriber_pid}" 2>/dev/null || true
sleep "$((shutdown_timeout_msec / 1000)).$(printf '%03d' "$((shutdown_timeout_msec % 1000))")"
kill -KILL "${subscriber_pid}" 2>/dev/null || true
