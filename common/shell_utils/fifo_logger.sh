#!/bin/bash

# Source this helper in a Bash service. SERVICE_FIFO_LOG_FILEPATH selects the
# service log path. FIFO_LOG_MAX_BYTES and FIFO_LOG_MAX_BACKUPS control rotation.
fifo_log_backup_list() {
    local path suffix
    for path in "$1".*; do
        [[ -f $path && ! -L $path ]] || continue
        suffix=${path##*.}
        if [[ $suffix =~ ^[0-9]{6}_[0-9]{6}$ ]]; then
            printf '1%s%s%s%s %s\n' "${suffix:4:2}" "${suffix:2:2}" "${suffix:0:2}" "${suffix:7}" "$suffix"
        elif [[ $suffix =~ ^[1-9][0-9]{0,3}$ ]]; then
            # Older releases used numbered backups, with .1 the newest.
            printf '0%04d %s\n' "$((10000 - suffix))" "$suffix"
        fi
    done | sort -r
}

fifo_log_rotate() {
    local log_file=$1 max_backups=$2 backup suffix count=0
    local -a backups=()
    mapfile -t backups < <(fifo_log_backup_list "$log_file")
    if [[ -e $log_file ]]; then
        if (( max_backups == 0 )); then
            rm -f -- "$log_file" || return
        else
            local TZ=UTC0 epoch latest latest_epoch
            printf -v epoch '%(%s)T' -1
            if [[ ${backups[0]:-} == 1* ]]; then
                latest=${backups[0]#* }
                latest_epoch=$(date -u -d "20${latest:4:2}-${latest:2:2}-${latest:0:2} ${latest:7:2}:${latest:9:2}:${latest:11:2}" +%s) || return
                if (( latest_epoch >= epoch )); then
                    epoch=$((latest_epoch + 1))
                fi
            fi
            printf -v suffix '%(%d%m%y_%H%M%S)T' "$epoch"
            while [[ -e $log_file.$suffix || -L $log_file.$suffix ]]; do
                ((epoch += 1))
                printf -v suffix '%(%d%m%y_%H%M%S)T' "$epoch"
            done
            mv -fT -- "$log_file" "$log_file.$suffix" || return
            count=1
        fi
    fi
    for backup in "${backups[@]}"; do
        if (( count >= max_backups )); then
            rm -f -- "$log_file.${backup#* }" || return
        fi
        ((count += 1))
    done
}

fifo_log_append() (
    LC_ALL=C
    umask 002
    local record=$1 startup=$2
    local log_file=${SERVICE_FIFO_LOG_FILEPATH:-${FIFO_LOG_FILE:-${WORK_DIR:-$PWD}/fifo_transactions.log}}
    local max_bytes=${FIFO_LOG_MAX_BYTES:-10485760}
    local max_backups=${FIFO_LOG_MAX_BACKUPS:-5}
    local header='TIMESTAMP,PID,OP,FIFO,SESSION_ID,EVENT,STATUS,QUERY,ANSWER,ANSWER_BASE64'
    local lock_fd size=0
    [[ $max_bytes =~ ^[1-9][0-9]{0,9}$ ]] || max_bytes=10485760
    [[ $max_backups =~ ^(0|[1-9][0-9]{0,3})$ ]] || max_backups=5
    [[ ! -L $log_file.lock && ( ! -e $log_file.lock || -f $log_file.lock ) ]] || exit 1
    exec {lock_fd}>>"$log_file.lock" || exit 1
    flock -x "$lock_fd" || exit 1

    [[ ! -L $log_file ]] || exit 1
    if [[ -e $log_file ]]; then
        [[ -f $log_file ]] || exit 1
        size=$(stat -c %s -- "$log_file") || exit 1
    fi
    if (( startup || (size > ${#header} + 2 && size + ${#record} > max_bytes) )); then
        fifo_log_rotate "$log_file" "$max_backups" || exit 1
        size=0
    fi
    if (( size == 0 )); then
        printf '%s\r\n' "$header" >>"$log_file" || exit 1
    fi
    printf '%s' "$record" >>"$log_file"
)

fifo_log_initialize() {
    fifo_log_append '' 1 2>/dev/null || :
}

fifo_log() {
    local timestamp field csv_record='' separator='' session_id=${3:-####}
    local query='' answer='' answer_base64=''
    [[ $session_id != "#####" ]] || session_id="####"
    case ${6:-} in
        query) query=$7 ;;
        answer) answer=$7 ;;
        answer_base64) answer_base64=${7//$'\n'/} ;;
    esac

    printf -v timestamp '%(%Y-%m-%dT%H:%M:%S%z)T' -1
    for field in "$timestamp" "$BASHPID" "$1" "$2" "$session_id" "$4" "${5:--}" "$query" "$answer" "$answer_base64"; do
        field=${field//\"/\"\"}
        csv_record+="$separator\"$field\""
        separator=,
    done
    fifo_log_append "$csv_record"$'\r\n' 0 2>/dev/null || :
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
