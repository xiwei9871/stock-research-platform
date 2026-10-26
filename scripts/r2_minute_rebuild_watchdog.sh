#!/usr/bin/env bash
# Watchdog for the R2 downstream qfq-minute rebuild.
# launchd StartInterval=300. Restarts the rebuild when it is not running,
# unless the run already completed or the stop file exists.
set -uo pipefail

ROOT="/Users/xiwei/stock_research"
LOG_DIR="$ROOT/outputs/research/data01r1_finance_q2_20261020"
RUN_LOG="$LOG_DIR/r2_downstream_minute.log"
WD_LOG="$ROOT/logs/r2_minute_rebuild_watchdog.log"
STOP_FILE="$LOG_DIR/r2_minute_rebuild_watchdog.stop"
COUNTER_FILE="$LOG_DIR/r2_minute_rebuild_watchdog.count"
LEDGER="$LOG_DIR/r2_downstream_minute_done.json"
STALL_SECONDS="${R2_MINUTE_WD_STALL_SECONDS:-5400}"   # 90min without ledger update -> restart
MAX_RESTARTS_PER_DAY="${R2_MINUTE_WD_MAX_RESTARTS:-20}"

mkdir -p "$ROOT/logs"

now() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "$(now) $*" >> "$WD_LOG"; }

if [ -f "$STOP_FILE" ]; then
  exit 0
fi

# Completed run: the driver prints this when the todo set is exhausted.
if [ -f "$RUN_LOG" ] && tail -5 "$RUN_LOG" | grep -q "minute phase done"; then
  log "done marker present, watchdog idle (remove $STOP_FILE check or add new pending work to resume)"
  exit 0
fi

PID="$(pgrep -f 'r2_downstream_rebuild.py minute' | head -1 || true)"

if [ -n "$PID" ]; then
  # running: stall = no stdout for STALL_SECONDS AND process old enough to have
  # produced output (grace period covers the ~2min signature-planning phase).
  # Ledger mtime is NOT the signal: FACTOR_GAP keys legitimately skip ledger
  # writes for long stretches while the process is healthy.
  proc_age="$(ps -o etimes= -p "$PID" 2>/dev/null | tr -d ' ' || echo 0)"
  if [ -f "$RUN_LOG" ]; then
    log_mtime="$(stat -f %m "$RUN_LOG")"
    quiet="$(( $(date +%s) - log_mtime ))"
  else
    quiet=999999
  fi
  if [ "${proc_age:-0}" -gt "$STALL_SECONDS" ] && [ "$quiet" -gt "$STALL_SECONDS" ]; then
    log "stall detected: pid=$PID proc_age=${proc_age}s log_quiet=${quiet}s — killing for restart"
    kill "$PID" 2>/dev/null || true
    sleep 5
    kill -9 "$PID" 2>/dev/null || true
  else
    exit 0
  fi
fi

# bound restart churn
today="$(date +%Y-%m-%d)"
count=0
if [ -f "$COUNTER_FILE" ]; then
  saved_day="$(cut -d' ' -f1 "$COUNTER_FILE")"
  saved_n="$(cut -d' ' -f2 "$COUNTER_FILE")"
  [ "$saved_day" = "$today" ] && count="$saved_n"
fi
if [ "$count" -ge "$MAX_RESTARTS_PER_DAY" ]; then
  log "restart budget exhausted ($count/$MAX_RESTARTS_PER_DAY today) — manual intervention required"
  exit 1
fi

count=$((count + 1))
echo "$today $count" > "$COUNTER_FILE"
cd "$ROOT"
nohup .venv/bin/python scripts/r2_revision/r2_downstream_rebuild.py minute \
  >> "$RUN_LOG" 2>&1 &
log "restarted minute rebuild pid=$! (restart #$count today)"
