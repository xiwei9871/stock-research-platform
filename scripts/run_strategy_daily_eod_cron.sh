#!/usr/bin/env bash
set -euo pipefail

ROOT="${STRATEGY_DAILY_EOD_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${STRATEGY_DAILY_EOD_PYTHON:-$ROOT/.venv/bin/python}"
LOG_DIR="${STRATEGY_DAILY_EOD_LOG_DIR:-$ROOT/logs}"
RUN_LOG="${STRATEGY_DAILY_EOD_RUN_LOG:-$LOG_DIR/strategy_daily_eod.host.log}"
TRADE_DATE="${STRATEGY_DAILY_EOD_TRADE_DATE:-}"
OUTPUT_ROOT="${STRATEGY_DAILY_EOD_OUTPUT_ROOT:-$ROOT/outputs/research/strategy_daily_eod}"

if [ -z "$TRADE_DATE" ]; then
  TRADE_DATE="$("$PYTHON" - <<'PY'
from stock_research.market_data import latest_complete_source_trade_date

trade_date = latest_complete_source_trade_date()
if not trade_date:
    raise SystemExit("could not resolve latest complete source trade date")
print(trade_date)
PY
)"
fi

source "$ROOT/scripts/stock_cron_guard.sh"
stock_cron_guard_or_exit "$PYTHON" "$TRADE_DATE" "${RESEARCH_SERVICE:-}"

mkdir -p "$LOG_DIR" "$(dirname "$RUN_LOG")" "$OUTPUT_ROOT"

set +e
{
  echo "=== strategy daily eod host run start: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
  echo "trade_date=$TRADE_DATE"
  cd "$ROOT"
  set +e
  "$PYTHON" -m stock_research.cli run-strategy-daily-eod \
    --trade-date "$TRADE_DATE" \
    --output-root "$OUTPUT_ROOT"
  rc=$?
  set -e
  echo "=== strategy daily eod host run end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ==="
  exit "$rc"
} 2>&1 | tee -a "$RUN_LOG"
pipeline_status=("${PIPESTATUS[@]}")
block_rc=${pipeline_status[0]}
tee_rc=${pipeline_status[1]}
set -e

if [ "$block_rc" -ne 0 ]; then
  exit "$block_rc"
fi
exit "$tee_rc"
