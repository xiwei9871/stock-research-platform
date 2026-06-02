#!/usr/bin/env bash
set -euo pipefail

ROOT="${MINUTE_BACKFILL_WATCHDOG_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${MINUTE_BACKFILL_WATCHDOG_PYTHON:-$ROOT/.venv/bin/python}"
OPENCLAW_BIN="${MINUTE_BACKFILL_WATCHDOG_OPENCLAW_BIN:-/Users/xiwei/stock_research/scripts/openclaw_runtime_cli.sh}"
LOG_DIR="${MINUTE_BACKFILL_WATCHDOG_LOG_DIR:-$ROOT/logs}"
RUN_LOG="${MINUTE_BACKFILL_WATCHDOG_RUN_LOG:-$LOG_DIR/minute_backfill_watchdog.host.log}"
START_DATE="${MINUTE_BACKFILL_WATCHDOG_START_DATE:-2024-01-01}"
END_DATE="${MINUTE_BACKFILL_WATCHDOG_END_DATE:-2026-05-13}"
FREQ="${MINUTE_BACKFILL_WATCHDOG_FREQ:-5min}"
ADJUST_TYPES="${MINUTE_BACKFILL_WATCHDOG_ADJUST_TYPES:-raw,qfq}"
MAX_JOBS="${MINUTE_BACKFILL_WATCHDOG_MAX_JOBS:-1200}"
WORKERS="${MINUTE_BACKFILL_WATCHDOG_WORKERS:-6}"
STALE_AFTER_MINUTES="${MINUTE_BACKFILL_WATCHDOG_STALE_AFTER_MINUTES:-20}"
RUN_TIMEOUT_SECONDS="${MINUTE_BACKFILL_WATCHDOG_RUN_TIMEOUT_SECONDS:-1800}"
COMPLETION_SENTINEL="${MINUTE_BACKFILL_WATCHDOG_COMPLETION_SENTINEL:-$LOG_DIR/minute_backfill_watchdog.completed}"
COMPLETION_KEY="${MINUTE_BACKFILL_WATCHDOG_COMPLETION_KEY:-minute|$START_DATE|$END_DATE|$FREQ|$ADJUST_TYPES|max$MAX_JOBS|workers$WORKERS|timeout$RUN_TIMEOUT_SECONDS}"
RUN_OUTPUT=""

mkdir -p "$LOG_DIR"

cleanup() {
  if [ -n "$RUN_OUTPUT" ]; then
    rm -f "$RUN_OUTPUT" 2>/dev/null || true
  fi
}
trap cleanup EXIT

{
  echo "=== minute backfill watchdog host run start: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
  echo "cwd=$ROOT"
  echo "python=$PYTHON"
  echo "openclaw_bin=$OPENCLAW_BIN"
  echo "completion_sentinel=$COMPLETION_SENTINEL"

  if [ -f "$COMPLETION_SENTINEL" ] && [ "$(cat "$COMPLETION_SENTINEL")" = "$COMPLETION_KEY" ]; then
    echo "skipped because backfill completion sentinel is current"
    echo "=== minute backfill watchdog host run end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=0 ==="
    exit 0
  fi

  cd "$ROOT"
  RUN_OUTPUT="$(mktemp "$LOG_DIR/minute_backfill_watchdog.XXXXXX")"

  set +e
  "$PYTHON" -m stock_research.cli backfill-watchdog \
    --adapter minute \
    --start-date "$START_DATE" \
    --end-date "$END_DATE" \
    --freq "$FREQ" \
    --adjust-types "$ADJUST_TYPES" \
    --max-jobs "$MAX_JOBS" \
    --workers "$WORKERS" \
    --stale-after-minutes "$STALE_AFTER_MINUTES" \
    --run-timeout-seconds "$RUN_TIMEOUT_SECONDS" \
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

  echo "=== minute backfill watchdog host run end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ==="
  exit "$rc"
} >> "$RUN_LOG" 2>&1
