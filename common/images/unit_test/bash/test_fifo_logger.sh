#!/bin/bash

source /tests/utils/shell_utils/fifo_logger.sh

setUp() {
    test_dir=$(mktemp -d)
    FIFO_LOG_FILE="$test_dir/fifo.log"
    unset FIFO_LOG_MAX_BYTES FIFO_LOG_MAX_BACKUPS SERVICE_FIFO_LOG_FILEPATH
}

tearDown() {
    rm -rf -- "$test_dir"
}

test_service_fifo_log_path_takes_precedence() {
    SERVICE_FIFO_LOG_FILEPATH="$test_dir/service hostname.log"
    fifo_log read /api/exec session received 0

    grep -Fq '"session","received","0",' "$SERVICE_FIFO_LOG_FILEPATH"
    assertEquals "service log contains the record" 0 "$?"
    assertFalse "legacy log path was unused" '[[ -e "$FIFO_LOG_FILE" ]]'
}

test_log_record_escapes_session_and_path() {
    fifo_log read '/api/with space/exec' $'session\nsecond line' received 0
    assertEquals $'TIMESTAMP,PID,OP,FIFO,SESSION_ID,EVENT,STATUS,QUERY,ANSWER,ANSWER_BASE64\r'         "$(head -n 1 "$FIFO_LOG_FILE")"
    python3 - "$FIFO_LOG_FILE" <<'EOF'
import csv
import sys

with open(sys.argv[1], newline="") as file:
    [record] = list(csv.reader(file))[1:]
assert record[1].isdigit()
assert record[2:7] == ["read", "/api/with space/exec", "session\nsecond line", "received", "0"]
EOF
    assertEquals "CSV reader recovers the multiline field" 0 "$?"
}

test_wrapper_preserves_stdout_stderr_and_exit_status() {
    fifo_logged write /api/result session bash -c \
        'printf "standard output\n"; printf "standard error\n" >&2; exit 17' \
        >"$test_dir/stdout" 2>"$test_dir/stderr"
    assertEquals 17 "$?"
    assertEquals 'standard output' "$(cat "$test_dir/stdout")"
    assertEquals 'standard error' "$(cat "$test_dir/stderr")"
    grep -q '"write","/api/result","session","started","-",' "$FIFO_LOG_FILE"
    assertEquals "start is logged" 0 "$?"
    grep -q '"write","/api/result","session","finished","17",' "$FIFO_LOG_FILE"
    assertEquals "failure status is logged" 0 "$?"
}

test_read_remains_in_calling_shell() {
    local payload
    IFS= fifo_logged read /api/exec '' read -r payload <<< '  request\text  '
    assertEquals 0 "$?"
    assertEquals '  request\text  ' "$payload"
    grep -F '"####","finished","0",' "$FIFO_LOG_FILE" >/dev/null
    assertEquals "successful read is logged" 0 "$?"
}

test_start_is_logged_before_opening_fifo() {
    local fifo="$test_dir/result" writer_pid
    mkfifo "$fifo"
    fifo_logged write "$fifo" session timeout 5 bash -c 'printf "%s" "reply" > "$1"' _ "$fifo" &
    writer_pid=$!

    local attempt
    for (( attempt=0; attempt<40; attempt++ )); do
        if [[ -s "$FIFO_LOG_FILE" ]]; then
            break
        fi
        sleep 0.05
    done
    grep -qs '"started",' "$FIFO_LOG_FILE"
    assertEquals "start is visible while the FIFO open blocks" 0 "$?"
    grep -qs '"finished",' "$FIFO_LOG_FILE"
    assertEquals "finish is pending until a reader opens the FIFO" 1 "$?"
    assertEquals reply "$(timeout 5 cat -- "$fifo")"
    wait "$writer_pid"
    assertEquals 0 "$?"
    grep -q '"finished","0",' "$FIFO_LOG_FILE"
    assertEquals "success is visible after FIFO I/O finishes" 0 "$?"
}

test_rotation_keeps_five_newest_backups() {
    FIFO_LOG_MAX_BYTES=160
    local session
    for session in 1 2 3 4 5 6 7; do
        fifo_log read /api/exec "$session" received 0
    done
    grep -q '"7","received",' "$FIFO_LOG_FILE"
    assertEquals "current file contains the newest event" 0 "$?"
    local backup index=6
    local -a backups
    mapfile -t backups < <(fifo_log_backup_list "$FIFO_LOG_FILE")
    assertEquals 5 "${#backups[@]}"
    for backup in "${backups[@]}"; do
        assertTrue 'archive uses a timestamp' '[[ ${backup#* } =~ ^[0-9]{6}_[0-9]{6}$ ]]'
        grep -Fq "\"$index\",\"received\"," "$FIFO_LOG_FILE.${backup#* }"
        assertEquals "archive contains event $index" 0 "$?"
        ((index -= 1))
    done
}

test_configurable_retention_and_file_modes() {
    FIFO_LOG_MAX_BYTES=1
    FIFO_LOG_MAX_BACKUPS=7
    local session
    for session in {1..8}; do
        fifo_log read /api/exec "$session" received 0
    done
    assertEquals 664 "$(stat -c %a -- "$FIFO_LOG_FILE")"
    local backup
    for backup in "$FIFO_LOG_FILE".[0-9]*; do
        assertEquals 664 "$(stat -c %a -- "$backup")"
    done
    assertEquals 7 "$(fifo_log_backup_list "$FIFO_LOG_FILE" | wc -l)"

    FIFO_LOG_MAX_BACKUPS=2
    fifo_log read /api/exec 9 received 0
    assertEquals 2 "$(find "$test_dir" -name 'fifo.log.[0-9]*' | wc -l)"

    FIFO_LOG_MAX_BACKUPS=0
    fifo_log read /api/exec 10 received 0
    assertEquals 0 "$(find "$test_dir" -name 'fifo.log.[0-9]*' | wc -l)"
    assertEquals 664 "$(stat -c %a -- "$FIFO_LOG_FILE")"
}

test_concurrent_writers_keep_all_records_during_rotation() {
    FIFO_LOG_MAX_BYTES=512
    local session pid
    local -a writers=()
    for session in {1..12}; do
        fifo_log read /api/exec "$session" received 0 &
        writers+=("$!")
    done
    for pid in "${writers[@]}"; do
        wait "$pid"
    done
    local -a backups=("$FIFO_LOG_FILE".[0-9]*)
    assertTrue "rotation occurred" '[[ -f "${backups[0]}" ]]'
    for session in {1..12}; do
        assertEquals "session $session has one record" 1 \
            "$(cat "$FIFO_LOG_FILE" "${backups[@]}" | grep -Fc "\"$session\",\"received\",\"0\",")"
    done
}

test_startup_backs_up_existing_log_and_writes_header() {
    printf '%s\n' 'previous container log' > "$FIFO_LOG_FILE"
    fifo_log_initialize

    local -a backups
    mapfile -t backups < <(fifo_log_backup_list "$FIFO_LOG_FILE")
    assertEquals 1 "${#backups[@]}"
    assertEquals 'previous container log' "$(cat "$FIFO_LOG_FILE.${backups[0]#* }")"
    assertEquals 1 "$(wc -l < "$FIFO_LOG_FILE")"
    assertEquals $'TIMESTAMP,PID,OP,FIFO,SESSION_ID,EVENT,STATUS,QUERY,ANSWER,ANSWER_BASE64\r'         "$(head -n 1 "$FIFO_LOG_FILE")"
}

test_log_failure_leaves_command_output_and_status_intact() {
    FIFO_LOG_FILE="$test_dir/missing/fifo.log"
    fifo_logged read /api/exec session bash -c 'printf "output\n"; exit 23' \
        >"$test_dir/stdout" 2>"$test_dir/stderr"
    assertEquals 23 "$?"
    assertEquals output "$(cat "$test_dir/stdout")"
    assertEquals '' "$(cat "$test_dir/stderr")"
}

. shunit2
