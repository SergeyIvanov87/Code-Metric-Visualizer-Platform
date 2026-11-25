#!/bin/bash

# Source this helper in a Bash service. SERVICE_FIFO_LOG_FILEPATH selects the
# service log path. FIFO_LOG_MAX_BYTES and FIFO_LOG_MAX_BACKUPS control rotation.
fifo_log() {
    local record payload_field session_id=${3:-####}
    [[ $session_id != "#####" ]] || session_id="####"
    printf -v record '%(%Y-%m-%dT%H:%M:%S%z)T SESSION_ID=%q PID=%s OP=%q FIFO=%q EVENT=%q STATUS=%q' \
        -1 "$session_id" "$BASHPID" "$1" "$2" "$4" "${5:--}"

    if [[ $# -ge 7 ]]; then
        local LC_ALL=C
        printf -v payload_field ' %s=%q' "$6" "$7"
        record+=$payload_field
    fi
    record+=$'\n'

    (
        LC_ALL=C
        umask 002
        local log_file=${SERVICE_FIFO_LOG_FILEPATH:-${FIFO_LOG_FILE:-${WORK_DIR:-$PWD}/fifo.log}}
        local max_bytes=${FIFO_LOG_MAX_BYTES:-10485760}
        local max_backups=${FIFO_LOG_MAX_BACKUPS:-5}
        local lock_fd size=0 backup backup_file backup_index
        [[ $max_bytes =~ ^[1-9][0-9]{0,9}$ ]] || max_bytes=10485760
        [[ $max_backups =~ ^(0|[1-9][0-9]{0,3})$ ]] || max_backups=5

        # Keep the lock on a separate inode that stays in place during rotation.
        [[ ! -e "$log_file.lock" || -f "$log_file.lock" ]] || exit 1
        exec {lock_fd}>>"$log_file.lock" || exit 1
        flock -x "$lock_fd" || exit 1

        if [[ -e "$log_file" ]]; then
            [[ -f "$log_file" ]] || exit 1
            size=$(stat -c %s -- "$log_file") || exit 1
        fi
        if (( size > 0 && size + ${#record} > max_bytes )); then
            for backup_file in "$log_file".*; do
                backup_index=${backup_file##*.}
                if [[ $backup_index =~ ^[1-9][0-9]{0,3}$ ]] && (( backup_index > max_backups )); then
                    rm -f -- "$backup_file" || exit 1
                fi
            done
            if (( max_backups == 0 )); then
                rm -f -- "$log_file" || exit 1
            else
                for (( backup=max_backups-1; backup>=1; backup-- )); do
                    if [[ -f "$log_file.$backup" ]]; then
                        mv -fT -- "$log_file.$backup" "$log_file.$((backup + 1))" || exit 1
                    fi
                done
                mv -fT -- "$log_file" "$log_file.1" || exit 1
            fi
        fi
        printf '%s' "$record" >>"$log_file"
    ) 2>/dev/null || :
}

# The result FIFO is either the base filename or that filename plus _SESSION_ID.
fifo_log_result() {
    local result_fifo=$1 base_result_fifo=$2 encoded_answer=$3
    local session_id='####' answer
    if [[ $result_fifo == "${base_result_fifo}_"* ]]; then
        session_id=${result_fifo#"${base_result_fifo}_"}
    fi

    # read preserves trailing newlines. Finding a NUL means the full answer
    # cannot be represented in a Bash variable, so retain its base64 encoding.
    if IFS= read -r -d '' answer < <(printf '%s' "$encoded_answer" | base64 -d); then
        fifo_log write "$result_fifo" "$session_id" finished 0 answer_base64 "$encoded_answer"
    else
        fifo_log write "$result_fifo" "$session_id" finished 0 answer "$answer"
    fi
}

fifo_write_result() {
    local result_fifo=$1 base_result_fifo=$2 session_id=$3 encoded_answer=$4 status
    fifo_log write "$result_fifo" "$session_id" started
    if printf '%s' "$encoded_answer" | base64 -d > "$result_fifo"; then
        fifo_log_result "$result_fifo" "$base_result_fifo" "$encoded_answer"
    else
        status=$?
        fifo_log write "$result_fifo" "$session_id" finished "$status"
        return "$status"
    fi
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
