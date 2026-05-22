#!/usr/bin/env bash
set -euo pipefail

ROOT="${TECHNICAL_FEATURE_WATCHDOG_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${TECHNICAL_FEATURE_WATCHDOG_PYTHON:-$ROOT/.venv/bin/python}"
OPENCLAW_BIN="${TECHNICAL_FEATURE_WATCHDOG_OPENCLAW_BIN:-/Users/xiwei/stock_research/scripts/openclaw_runtime_cli.sh}"
LOG_DIR="${TECHNICAL_FEATURE_WATCHDOG_LOG_DIR:-$ROOT/logs}"
RUN_LOG="${TECHNICAL_FEATURE_WATCHDOG_RUN_LOG:-$LOG_DIR/technical_feature_backfill_watchdog.host.log}"
LOCK_PATH="${TECHNICAL_FEATURE_WATCHDOG_LOCK_DIR:-$LOG_DIR/technical_feature_backfill_watchdog.lock}"
START_INTERVAL_SECONDS="${TECHNICAL_FEATURE_WATCHDOG_START_INTERVAL_SECONDS:-300}"
SLEEP_BETWEEN_RUNS_SECONDS="${TECHNICAL_FEATURE_WATCHDOG_SLEEP_BETWEEN_RUNS_SECONDS:-0}"
START_DATE="${TECHNICAL_FEATURE_WATCHDOG_START_DATE:-1991-01-01}"
END_DATE="${TECHNICAL_FEATURE_WATCHDOG_END_DATE:-2026-05-14}"
ADJUST_TYPE="${TECHNICAL_FEATURE_WATCHDOG_ADJUST_TYPE:-qfq}"
LOOKBACK_BARS="${TECHNICAL_FEATURE_WATCHDOG_LOOKBACK_BARS:-260}"
SOURCE_DATA_VERSION="${TECHNICAL_FEATURE_WATCHDOG_SOURCE_DATA_VERSION:-market_daily_bar:qfq}"
MAX_JOBS="${TECHNICAL_FEATURE_WATCHDOG_MAX_JOBS:-30}"
WORKERS="${TECHNICAL_FEATURE_WATCHDOG_WORKERS:-5}"
STALE_AFTER_MINUTES="${TECHNICAL_FEATURE_WATCHDOG_STALE_AFTER_MINUTES:-20}"
RUN_TIMEOUT_SECONDS="${TECHNICAL_FEATURE_WATCHDOG_RUN_TIMEOUT_SECONDS:-1200}"
COMPLETION_SENTINEL="${TECHNICAL_FEATURE_WATCHDOG_COMPLETION_SENTINEL:-$LOG_DIR/technical_feature_backfill_watchdog.completed}"
COMPLETION_KEY="${TECHNICAL_FEATURE_WATCHDOG_COMPLETION_KEY:-technical-features|$START_DATE|$END_DATE|$ADJUST_TYPE|$SOURCE_DATA_VERSION|lookback$LOOKBACK_BARS|max$MAX_JOBS|workers$WORKERS|timeout$RUN_TIMEOUT_SECONDS}"
RUN_OUTPUT=""

mkdir -p "$LOG_DIR"
mkdir -p "$(dirname "$RUN_LOG")"

exec >> "$RUN_LOG" 2>&1

echo "=== technical feature backfill watchdog host run start: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
echo "cwd=$ROOT"
echo "python=$PYTHON"
echo "openclaw_bin=$OPENCLAW_BIN"
echo "lock_path=$LOCK_PATH"
echo "start_interval_seconds=$START_INTERVAL_SECONDS"
echo "sleep_between_runs_seconds=$SLEEP_BETWEEN_RUNS_SECONDS"
echo "completion_sentinel=$COMPLETION_SENTINEL"

if [ -f "$COMPLETION_SENTINEL" ] && [ "$(cat "$COMPLETION_SENTINEL")" = "$COMPLETION_KEY" ]; then
  echo "skipped because backfill completion sentinel is current"
  echo "=== technical feature backfill watchdog host run end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=0 ==="
  exit 0
fi

if mkdir "$LOCK_PATH" 2>/dev/null; then
  whether_lock_acquired=true
else
  whether_lock_acquired=false
fi
echo "whether_lock_acquired=$whether_lock_acquired"

if [ "$whether_lock_acquired" != "true" ]; then
  echo "skipped because another technical-feature watchdog is running"
  echo "=== technical feature backfill watchdog host run end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=0 ==="
  exit 0
fi

cleanup() {
  rmdir "$LOCK_PATH" 2>/dev/null || true
  if [ -n "$RUN_OUTPUT" ]; then
    rm -f "$RUN_OUTPUT" 2>/dev/null || true
  fi
}
trap cleanup EXIT

cd "$ROOT"
RUN_OUTPUT="$(mktemp "$LOG_DIR/technical_feature_backfill_watchdog.XXXXXX")"

set +e
"$PYTHON" -m stock_research.cli backfill-watchdog \
  --adapter technical-features \
  --start-date "$START_DATE" \
  --end-date "$END_DATE" \
  --adjust-type "$ADJUST_TYPE" \
  --lookback-bars "$LOOKBACK_BARS" \
  --source-data-version "$SOURCE_DATA_VERSION" \
  --max-jobs "$MAX_JOBS" \
  --workers "$WORKERS" \
  --stale-after-minutes "$STALE_AFTER_MINUTES" \
  --run-timeout-seconds "$RUN_TIMEOUT_SECONDS" \
  --sleep-between-runs-seconds "$SLEEP_BETWEEN_RUNS_SECONDS" \
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

echo "=== technical feature backfill watchdog host run end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ==="
exit "$rc"
