#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
TRADE_DATE="${TRADE_DATE:-}"
LOG_DIR="${LOG_DIR:-$ROOT/logs/minute_daily}"
RUN_LOG="${RUN_LOG:-$LOG_DIR/baostock_minute_daily_cron.log}"

source "$ROOT/scripts/stock_cron_guard.sh"
clear_stock_proxy_env
stock_cron_guard_or_exit "$PYTHON_BIN" "$TRADE_DATE" "${RESEARCH_SERVICE:-}"

mkdir -p "$LOG_DIR" "$(dirname "$RUN_LOG")"

cmd=("$PYTHON_BIN" -m stock_research.cli run-baostock-minute-daily)
if [[ -n "$TRADE_DATE" ]]; then
  cmd+=(--trade-date "$TRADE_DATE")
fi

set +e
{
  echo "=== baostock minute daily start: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
  echo "trade_date=${TRADE_DATE:-auto}"
  set +e
  "${cmd[@]}"
  rc=$?
  set -e
  echo "=== baostock minute daily end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ==="
  exit "$rc"
} 2>&1 | tee -a "$RUN_LOG"
pipeline_status=("${PIPESTATUS[@]}")
block_rc=${pipeline_status[0]}
tee_rc=${pipeline_status[1]}
set -e

if [[ "$block_rc" -ne 0 ]]; then
  exit "$block_rc"
fi
exit "$tee_rc"
