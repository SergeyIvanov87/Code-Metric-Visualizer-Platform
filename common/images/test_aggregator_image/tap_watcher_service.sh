#!/bin/bash

# Observe Envoy's per-connection tap files. Envoy's downstream byte counter
# keeps the service alive; a trace is decoded only after Envoy closes it.

tap_path=$1
decoded_path=$2
quiet_msec=$3
result_path=$4
max_wait_msec=${5:-900000}
envoy_admin_url=${6:-http://127.0.0.1:9901}
connection_backup_path=${7:-${decoded_path}/connections}

quiet_seconds=$(( (quiet_msec + 999) / 1000 ))
max_wait_seconds=$(( (max_wait_msec + 999) / 1000 ))
(( quiet_seconds < 1 )) && quiet_seconds=1
(( max_wait_seconds < quiet_seconds )) && max_wait_seconds=$quiet_seconds

mkdir -p "${tap_path}" "${decoded_path}" "${connection_backup_path}" "${result_path}"

declare -A active_files
declare -a workers
start_second=$SECONDS
last_activity_second=$SECONDS
last_stats_poll_second=-1
last_rx_bytes=
stats_ready=0
capture_stop_requested=0
capture_stop_second=0
shutdown_grace_seconds=30

coproc TAP_EVENTS {
    inotifywait --monitor \
        --event create --event close_write \
        --format '%e|%w%f' "${tap_path}" 2>&1
}
event_fd=${TAP_EVENTS[0]}
inotify_pid=$TAP_EVENTS_PID

# inotifywait announces this only after the kernel watch has been installed.
# Bootstrap waits for the marker so Envoy cannot win a startup race.
watch_established=0
while IFS= read -r monitor_status <&${event_fd}; do
    if [[ "${monitor_status}" == "Watches established." ]]; then
        watch_established=1
        break
    fi
done
if (( watch_established == 0 )); then
    echo "inotifywait exited before establishing the tap directory watch" \
        > "${result_path}/result_log_stderr"
    echo 255 > "${result_path}/result"
    exit 255
fi
: > "${result_path}/watcher_ready"


while true; do
    if IFS='|' read -r -t 1 event_name event_path <&${event_fd}; then
        case "${event_name}" in
            *CREATE*)
                active_files["${event_path}"]=1
                ;;
        esac
        case "${event_name}" in
            *CLOSE_WRITE*)
                unset 'active_files['"${event_path}"']'
                base_name=$(basename "${event_path}")
                output_file="${connection_backup_path}/${base_name%.*}.log"
                error_file="${result_path}/${base_name}.decode_stderr"
                python3 /package/decode_envoy_tap.py "${event_path}" "${output_file}" \
                    --name-by-producer \
                    > /dev/null 2> "${error_file}" &
                workers+=("$!")
                ;;
        esac
    fi

    if (( SECONDS - start_second >= max_wait_seconds )); then
        echo "Timed out waiting for Envoy tap connections to close" \
            > "${result_path}/result_log_stderr"
        echo 255 > "${result_path}/result"
        kill "${inotify_pid}" 2>/dev/null
        kill -s SIGTERM "$(pidof envoy)" 2>/dev/null
        exit 255
    fi

    # File-per-tap output is buffered by Envoy, so inotify MODIFY events are
    # not a reliable indication of live traffic. Poll the TCP proxy's
    # monotonic downstream byte counter instead.
    if (( SECONDS != last_stats_poll_second )); then
        last_stats_poll_second=$SECONDS
        current_rx_bytes=$(
            curl --silent --fail --max-time 1 --get \
                --data-urlencode 'filter=^tcp\.destination\.downstream_cx_rx_bytes_total$' \
                "${envoy_admin_url}/stats" 2>/dev/null |
                awk -F': ' \
                    '$1 == "tcp.destination.downstream_cx_rx_bytes_total" { print $2; exit }'
        )
        if [[ "${current_rx_bytes}" =~ ^[0-9]+$ ]]; then
            if (( stats_ready == 0 )); then
                stats_ready=1
                last_rx_bytes=$current_rx_bytes
                last_activity_second=$SECONDS
            elif [[ "${current_rx_bytes}" != "${last_rx_bytes}" ]]; then
                last_rx_bytes=$current_rx_bytes
                last_activity_second=$SECONDS
            fi
        fi
    fi

    if (( capture_stop_requested != 0 )); then
        if (( ${#active_files[@]} == 0 )); then
            break
        fi
        if (( SECONDS - capture_stop_second >= shutdown_grace_seconds )); then
            echo "Envoy did not close all tap files after capture stopped" \
                > "${result_path}/result_log_stderr"
            echo 255 > "${result_path}/result"
            kill "${inotify_pid}" 2>/dev/null
            exit 255
        fi
    elif (( stats_ready != 0 && SECONDS - last_activity_second >= quiet_seconds )); then
        # Persistent Docker logger connections keep tap files open after tests
        # finish. Ask bootstrap to stop Envoy after the global traffic-quiet
        # period; its shutdown closes every trace before decoding starts.
        : > "${result_path}/capture_stop_requested"
        capture_stop_requested=1
        capture_stop_second=$SECONDS
    fi
done

kill "${inotify_pid}" 2>/dev/null
wait "${inotify_pid}" 2>/dev/null
rm -f "${result_path}/watcher_ready"

decode_status=0
for worker in "${workers[@]}"; do
    wait "${worker}" || decode_status=1
done

if (( decode_status != 0 )); then
    {
        echo "One or more Envoy tap traces could not be decoded"
        for error_file in "${result_path}"/*.decode_stderr; do
            if [[ -s "${error_file}" ]]; then
                echo "${error_file}:"
                cat "${error_file}"
            fi
        done
    } > "${result_path}/result_log_stderr"
    : > "${result_path}/result_log_stdout"
    echo 255 > "${result_path}/result"
else
    # Preserve every decoded connection, then publish one ordered file per
    # producer for the test-result aggregator.
    python3 /package/aggregate_connection_logs.py \
        "${connection_backup_path}" "${decoded_path}"
    /package/log_watcher_service.sh "${decoded_path}" 1 "${result_path}"
fi

kill -s SIGTERM "$(pidof envoy)" 2>/dev/null
exit "$(cat "${result_path}/result")"
