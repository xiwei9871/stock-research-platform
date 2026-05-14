#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/xiwei/stock_research"
PYTHON="$ROOT/.venv/bin/python"
OPENCLAW_BIN="/Users/xiwei/.local/bin/openclaw"
LOG_DIR="$ROOT/logs"
RUN_LOG="$LOG_DIR/minute_backfill_watchdog.host.log"

mkdir -p "$LOG_DIR"

{
  echo "=== minute backfill watchdog host run start: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
  echo "cwd=$ROOT"
  echo "python=$PYTHON"
  echo "openclaw_bin=$OPENCLAW_BIN"
  cd "$ROOT"

  set +e
  "$PYTHON" -m stock_research.cli backfill-watchdog \
    --adapter minute \
    --start-date 2024-01-01 \
    --end-date 2026-05-13 \
    --freq 5min \
    --adjust-types raw,qfq \
    --max-jobs 1200 \
    --workers 6 \
    --stale-after-minutes 20 \
    --run-timeout-seconds 1800 \
    --report-target chat:oc_82dd978138a0cde5864868c5b5b8e754 \
    --report-account jarvis \
    --openclaw-bin "$OPENCLAW_BIN"
  rc=$?
  set -e

  echo "=== minute backfill watchdog host run end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ==="
  exit "$rc"
} >> "$RUN_LOG" 2>&1
