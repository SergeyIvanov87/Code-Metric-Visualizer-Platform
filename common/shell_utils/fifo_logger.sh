#!/bin/bash

# Source this helper in a Bash service. FIFO_LOG_FILE overrides the default
# service log path and FIFO_LOG_MAX_BYTES sets the size before rotation.
fifo_log() {
    local record
    printf -v record '%(%Y-%m-%dT%H:%M:%S%z)T session_id=%q pid=%s operation=%q fifo=%q event=%q status=%q\n' \
        -1 "${3:-unknown}" "$BASHPID" "$1" "$2" "$4" "${5:--}"

    (
        LC_ALL=C
        umask 077
        local log_file=${FIFO_LOG_FILE:-${WORK_DIR:-$PWD}/fifo.log}
        local max_bytes=${FIFO_LOG_MAX_BYTES:-10485760}
        local lock_fd size=0 backup
        [[ $max_bytes =~ ^[1-9][0-9]{0,9}$ ]] || max_bytes=10485760

        # Keep the lock on a separate inode that stays in place during rotation.
        [[ ! -e "$log_file.lock" || -f "$log_file.lock" ]] || exit 1
        exec {lock_fd}>>"$log_file.lock" || exit 1
        flock -x "$lock_fd" || exit 1

        if [[ -e "$log_file" ]]; then
            [[ -f "$log_file" ]] || exit 1
            size=$(stat -c %s -- "$log_file") || exit 1
        fi
        if (( size > 0 && size + ${#record} > max_bytes )); then
            for (( backup=4; backup>=1; backup-- )); do
                if [[ -f "$log_file.$backup" ]]; then
                    mv -fT -- "$log_file.$backup" "$log_file.$((backup + 1))" || exit 1
                fi
            done
            mv -fT -- "$log_file" "$log_file.1" || exit 1
        fi
        printf '%s' "$record" >>"$log_file"
    ) 2>/dev/null || :
}

fifo_logged() {
    local fifo_operation=$1 fifo_path=$2 fifo_session=$3 fifo_status
    shift 3

    fifo_log "$fifo_operation" "$fifo_path" "$fifo_session" started
    if "$@"; then
        fifo_status=0
    else
        fifo_status=$?
    fi
    fifo_log "$fifo_operation" "$fifo_path" "$fifo_session" finished "$fifo_status"
    return "$fifo_status"
}
