#!/usr/bin/env bash
set -euo pipefail

ROOT="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_PYTHON:-$ROOT/.venv/bin/python}"
OPENCLAW_BIN="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_OPENCLAW_BIN:-/Users/xiwei/stock_research/scripts/openclaw_runtime_cli.sh}"
LOG_DIR="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_LOG_DIR:-$ROOT/logs}"
RUN_LOG="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_RUN_LOG:-$LOG_DIR/baostock_minute_backfill_watchdog.host.log}"
START_DATE="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_START_DATE:-2020-01-02}"
END_DATE="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_END_DATE:-$(date +%F)}"
FREQ="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_FREQ:-5min}"
ADJUST_TYPES="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_ADJUST_TYPES:-raw,qfq}"
TODAY_ADJUST_TYPES="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_TODAY_ADJUST_TYPES:-raw,qfq}"
MAX_JOBS="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_MAX_JOBS:-1200}"
WORKERS="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_WORKERS:-8}"
STALE_AFTER_MINUTES="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_STALE_AFTER_MINUTES:-20}"
RUN_TIMEOUT_SECONDS="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_RUN_TIMEOUT_SECONDS:-1800}"
DAILY_REQUEST_LIMIT="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_DAILY_REQUEST_LIMIT:-50000}"
SAFETY_MULTIPLIER="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_SAFETY_MULTIPLIER:-1.1}"
MAX_DAILY_BACKFILL_REQUESTS="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_MAX_DAILY_BACKFILL_REQUESTS:-}"
REQUEST_LEDGER_PATH="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_REQUEST_LEDGER_PATH:-$LOG_DIR/baostock_minute_request_quota.json}"
COMPLETION_SENTINEL="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_COMPLETION_SENTINEL:-$LOG_DIR/baostock_minute_backfill_watchdog.completed}"
COMPLETION_KEY="${BAOSTOCK_MINUTE_BACKFILL_WATCHDOG_COMPLETION_KEY:-baostock-minute|$START_DATE|$END_DATE|$FREQ|$ADJUST_TYPES|today$TODAY_ADJUST_TYPES|max$MAX_JOBS|workers$WORKERS|limit$DAILY_REQUEST_LIMIT|safety$SAFETY_MULTIPLIER|timeout$RUN_TIMEOUT_SECONDS}"
RUN_OUTPUT=""

mkdir -p "$LOG_DIR"

cleanup() {
  if [ -n "$RUN_OUTPUT" ]; then
    rm -f "$RUN_OUTPUT" 2>/dev/null || true
  fi
}
trap cleanup EXIT

{
  echo "=== baostock minute backfill watchdog host run start: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
  echo "cwd=$ROOT"
  echo "python=$PYTHON"
  echo "openclaw_bin=$OPENCLAW_BIN"
  echo "request_ledger_path=$REQUEST_LEDGER_PATH"
  echo "completion_sentinel=$COMPLETION_SENTINEL"

  if [ -f "$COMPLETION_SENTINEL" ] && [ "$(cat "$COMPLETION_SENTINEL")" = "$COMPLETION_KEY" ]; then
    echo "skipped because backfill completion sentinel is current"
    echo "=== baostock minute backfill watchdog host run end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=0 ==="
    exit 0
  fi

  cd "$ROOT"
  RUN_OUTPUT="$(mktemp "$LOG_DIR/baostock_minute_backfill_watchdog.XXXXXX")"

  extra_args=()
  if [ -n "$MAX_DAILY_BACKFILL_REQUESTS" ]; then
    extra_args+=(--max-daily-backfill-requests "$MAX_DAILY_BACKFILL_REQUESTS")
  fi

  set +e
  "$PYTHON" -m stock_research.cli baostock-minute-backfill-watchdog \
    --start-date "$START_DATE" \
    --end-date "$END_DATE" \
    --freq "$FREQ" \
    --adjust-types "$ADJUST_TYPES" \
    --max-jobs "$MAX_JOBS" \
    --workers "$WORKERS" \
    --stale-after-minutes "$STALE_AFTER_MINUTES" \
    --run-timeout-seconds "$RUN_TIMEOUT_SECONDS" \
    --baostock-daily-request-limit "$DAILY_REQUEST_LIMIT" \
    --baostock-safety-multiplier "$SAFETY_MULTIPLIER" \
    --today-adjust-types "$TODAY_ADJUST_TYPES" \
    --request-ledger-path "$REQUEST_LEDGER_PATH" \
    ${extra_args[@]+"${extra_args[@]}"} \
    --report-target chat:oc_82dd978138a0cde5864868c5b5b8e754 \
    --report-account jarvis \
    --openclaw-bin "$OPENCLAW_BIN" 2>&1 | tee "$RUN_OUTPUT"
  rc=${PIPESTATUS[0]}
  set -e

  if [ "$rc" -eq 0 ] \
    && grep -Eq '\|action\|healthy$' "$RUN_OUTPUT" \
    && grep -Eq '\|work_remaining\|False$' "$RUN_OUTPUT"; then
    printf '%s\n' "$COMPLETION_KEY" > "$COMPLETION_SENTINEL"
    echo "completion_sentinel_written=true"
  else
    echo "completion_sentinel_written=false"
  fi

  echo "=== baostock minute backfill watchdog host run end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ==="
  exit "$rc"
} >> "$RUN_LOG" 2>&1
