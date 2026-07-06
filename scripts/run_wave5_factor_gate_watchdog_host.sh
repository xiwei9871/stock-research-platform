#!/usr/bin/env bash
set -euo pipefail

ROOT="${FACTOR_GATE_WATCHDOG_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${FACTOR_GATE_WATCHDOG_PYTHON:-$ROOT/.venv/bin/python}"
OPENCLAW_BIN="${FACTOR_GATE_WATCHDOG_OPENCLAW_BIN:-/Users/xiwei/stock_research/scripts/openclaw_runtime_cli.sh}"
LOG_DIR="${FACTOR_GATE_WATCHDOG_LOG_DIR:-$ROOT/logs/full_history_completion}"
RUN_LOG="${FACTOR_GATE_WATCHDOG_RUN_LOG:-$LOG_DIR/wave5-factor-gate-watchdog.host.log}"
START_DATE="${FACTOR_GATE_WATCHDOG_START_DATE:-1991-06-24}"
END_DATE="${FACTOR_GATE_WATCHDOG_END_DATE:-2026-04-28}"
VALIDATION_START_DATE="${FACTOR_GATE_WATCHDOG_VALIDATION_START_DATE:-2018-01-01}"
HORIZONS="${FACTOR_GATE_WATCHDOG_HORIZONS:-5,10,20,60}"
PRIMARY_HORIZON="${FACTOR_GATE_WATCHDOG_PRIMARY_HORIZON:-5}"
CALC_VERSION="${FACTOR_GATE_WATCHDOG_CALC_VERSION:-v1}"
SCORE_VERSION="${FACTOR_GATE_WATCHDOG_SCORE_VERSION:-manual_v1}"
QUANTILES="${FACTOR_GATE_WATCHDOG_QUANTILES:-5}"
TOP_N="${FACTOR_GATE_WATCHDOG_TOP_N:-30}"
MAX_JOBS="${FACTOR_GATE_WATCHDOG_MAX_JOBS:-1}"
WORKERS="${FACTOR_GATE_WATCHDOG_WORKERS:-1}"
STALE_AFTER_MINUTES="${FACTOR_GATE_WATCHDOG_STALE_AFTER_MINUTES:-20}"
RUN_TIMEOUT_SECONDS="${FACTOR_GATE_WATCHDOG_RUN_TIMEOUT_SECONDS:-7200}"
COMPLETION_SENTINEL="${FACTOR_GATE_WATCHDOG_COMPLETION_SENTINEL:-$LOG_DIR/wave5-factor-gate-watchdog.completed}"
COMPLETION_KEY="${FACTOR_GATE_WATCHDOG_COMPLETION_KEY:-factor-gate|$START_DATE|$END_DATE|validation$VALIDATION_START_DATE|h$HORIZONS|primary$PRIMARY_HORIZON|$SCORE_VERSION|$CALC_VERSION|max$MAX_JOBS|workers$WORKERS|timeout$RUN_TIMEOUT_SECONDS}"
SMOKE_ONLY="${FACTOR_GATE_WATCHDOG_SMOKE_ONLY:-0}"
RUN_OUTPUT=""

mkdir -p "$LOG_DIR"

cleanup() {
  if [ -n "$RUN_OUTPUT" ]; then
    rm -f "$RUN_OUTPUT" 2>/dev/null || true
  fi
}
trap cleanup EXIT

{
  echo "=== factor gate backfill watchdog host run start: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
  echo "cwd=$ROOT"
  echo "python=$PYTHON"
  echo "openclaw_bin=$OPENCLAW_BIN"
  echo "completion_sentinel=$COMPLETION_SENTINEL"

  if [ "$SMOKE_ONLY" = "1" ]; then
    echo "factor_gate_watchdog|smoke|would_run|adapter=factor-gate|start_date=$START_DATE|end_date=$END_DATE|validation_start_date=$VALIDATION_START_DATE|max_jobs=$MAX_JOBS|workers=$WORKERS"
    echo "=== factor gate backfill watchdog host run end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=0 ==="
    exit 0
  fi

  if [ -f "$COMPLETION_SENTINEL" ] && [ "$(cat "$COMPLETION_SENTINEL")" = "$COMPLETION_KEY" ]; then
    echo "skipped because backfill completion sentinel is current"
    echo "=== factor gate backfill watchdog host run end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=0 ==="
    exit 0
  fi

  cd "$ROOT"
  RUN_OUTPUT="$(mktemp "$LOG_DIR/wave5_factor_gate_watchdog.XXXXXX")"

  set +e
  "$PYTHON" -m stock_research.cli backfill-watchdog \
    --adapter factor-gate \
    --start-date "$START_DATE" \
    --end-date "$END_DATE" \
    --validation-start-date "$VALIDATION_START_DATE" \
    --horizons "$HORIZONS" \
    --primary-horizon "$PRIMARY_HORIZON" \
    --calc-version "$CALC_VERSION" \
    --score-version "$SCORE_VERSION" \
    --quantiles "$QUANTILES" \
    --top-n "$TOP_N" \
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

  echo "=== factor gate backfill watchdog host run end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ==="
  exit "$rc"
} >> "$RUN_LOG" 2>&1
