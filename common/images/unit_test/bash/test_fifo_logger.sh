#!/bin/bash

source /tests/utils/shell_utils/fifo_logger.sh

setUp() {
    test_dir=$(mktemp -d)
    FIFO_LOG_FILE="$test_dir/fifo.log"
    unset FIFO_LOG_MAX_BYTES
}

tearDown() {
    rm -rf -- "$test_dir"
}

test_log_record_escapes_session_and_path() {
    fifo_log read '/api/with space/exec' $'session\nsecond line' received 0
    assertEquals 1 "$(wc -l < "$FIFO_LOG_FILE" | tr -d ' ')"
    grep -F 'session_id=$'\''session\nsecond line'\''' "$FIFO_LOG_FILE" >/dev/null
    assertEquals "session ID is escaped on one line" 0 "$?"
    grep -F 'operation=read fifo=/api/with\ space/exec event=received status=0' "$FIFO_LOG_FILE" >/dev/null
    assertEquals "operation, FIFO path, event and status are present" 0 "$?"
}

test_wrapper_preserves_stdout_stderr_and_exit_status() {
    fifo_logged write /api/result session bash -c \
        'printf "standard output\n"; printf "standard error\n" >&2; exit 17' \
        >"$test_dir/stdout" 2>"$test_dir/stderr"
    assertEquals 17 "$?"
    assertEquals 'standard output' "$(cat "$test_dir/stdout")"
    assertEquals 'standard error' "$(cat "$test_dir/stderr")"
    grep -q 'session_id=session .* operation=write fifo=/api/result event=started status=-$' "$FIFO_LOG_FILE"
    assertEquals "start is logged" 0 "$?"
    grep -q 'session_id=session .* operation=write fifo=/api/result event=finished status=17$' "$FIFO_LOG_FILE"
    assertEquals "failure status is logged" 0 "$?"
}

test_read_remains_in_calling_shell() {
    local payload
    IFS= fifo_logged read /api/exec '' read -r payload <<< '  request\text  '
    assertEquals 0 "$?"
    assertEquals '  request\text  ' "$payload"
    grep -q 'session_id=unknown .* event=finished status=0$' "$FIFO_LOG_FILE"
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
    grep -qs 'event=started' "$FIFO_LOG_FILE"
    assertEquals "start is visible while the FIFO open blocks" 0 "$?"
    grep -qs 'event=finished' "$FIFO_LOG_FILE"
    assertEquals "finish is pending until a reader opens the FIFO" 1 "$?"
    assertEquals reply "$(timeout 5 cat -- "$fifo")"
    wait "$writer_pid"
    assertEquals 0 "$?"
    grep -q 'event=finished status=0$' "$FIFO_LOG_FILE"
    assertEquals "success is visible after FIFO I/O finishes" 0 "$?"
}

test_rotation_keeps_five_newest_backups() {
    FIFO_LOG_MAX_BYTES=160
    local session
    for session in 1 2 3 4 5 6 7; do
        fifo_log read /api/exec "$session" received 0
    done
    grep -q 'session_id=7 ' "$FIFO_LOG_FILE"
    assertEquals "current file contains the newest event" 0 "$?"
    local backup
    for backup in 1 2 3 4 5; do
        grep -q "session_id=$((7 - backup)) " "$FIFO_LOG_FILE.$backup"
        assertEquals "backup $backup contains the expected event" 0 "$?"
    done
    assertFalse "there is no sixth backup" "[[ -e \"$FIFO_LOG_FILE.6\" ]]"
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
    assertTrue "rotation occurred" "[[ -f \"$FIFO_LOG_FILE.1\" ]]"
    for session in {1..12}; do
        assertEquals "session $session has one record" 1 \
            "$(cat "$FIFO_LOG_FILE" "$FIFO_LOG_FILE".[1-5] | grep -c "session_id=$session .* event=received status=0$")"
    done
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
