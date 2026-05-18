#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/xiwei/stock_research"
PYTHON="$ROOT/.venv/bin/python"
OPENCLAW_BIN="/Users/xiwei/stock_research/scripts/openclaw_runtime_cli.sh"
LOG_DIR="$ROOT/logs/full_history_completion"
RUN_LOG="$LOG_DIR/wave5-factor-gate-watchdog.host.log"

mkdir -p "$LOG_DIR"

{
  echo "=== factor gate backfill watchdog host run start: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
  echo "cwd=$ROOT"
  echo "python=$PYTHON"
  echo "openclaw_bin=$OPENCLAW_BIN"
  cd "$ROOT"

  set +e
  "$PYTHON" -m stock_research.cli backfill-watchdog \
    --adapter factor-gate \
    --start-date 1991-06-24 \
    --end-date 2026-04-28 \
    --validation-start-date 2018-01-01 \
    --horizons 5,10,20,60 \
    --primary-horizon 5 \
    --calc-version v1 \
    --score-version manual_v1 \
    --quantiles 5 \
    --top-n 30 \
    --max-jobs 1 \
    --workers 1 \
    --stale-after-minutes 20 \
    --run-timeout-seconds 7200 \
    --report-target chat:oc_82dd978138a0cde5864868c5b5b8e754 \
    --report-account jarvis \
    --openclaw-bin "$OPENCLAW_BIN"
  rc=$?
  set -e

  echo "=== factor gate backfill watchdog host run end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ==="
  exit "$rc"
} >> "$RUN_LOG" 2>&1
