#!/usr/bin/env bash
set -euo pipefail

ROOT="${PLATFORM_READY_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${PLATFORM_READY_PYTHON:-$ROOT/.venv/bin/python}"
LOG_DIR="${PLATFORM_READY_LOG_DIR:-$ROOT/logs}"
RUN_LOG="${PLATFORM_READY_CHECK_RUN_LOG:-$LOG_DIR/platform_ready_check.host.log}"
TRADE_DATE="${PLATFORM_READY_TRADE_DATE:-}"
REPORTS_DIR="${PLATFORM_READY_REPORTS_DIR:-$ROOT/reports}"
OUTPUT_DIR="${PLATFORM_READY_OUTPUT_DIR:-$ROOT/outputs/research}"

if [ -z "$TRADE_DATE" ]; then
  TRADE_DATE="$("$PYTHON" - <<'PY'
from stock_research.daily_close_pipeline import PipelineConfig, parse_trade_date
config = PipelineConfig()
print(parse_trade_date(None, config.timezone).isoformat())
PY
)"
fi

mkdir -p "$LOG_DIR" "$OUTPUT_DIR" "$(dirname "$RUN_LOG")"

set +e
{
  echo "=== platform ready check start: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
  cd "$ROOT"
  "$PYTHON" -m stock_research.platform_ready \
    --trade-date "$TRADE_DATE" \
    --reports-dir "$REPORTS_DIR" \
    --json-output "$OUTPUT_DIR/platform_ready_${TRADE_DATE}.json"
  rc=$?
  echo "=== platform ready check end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ==="
  exit "$rc"
} 2>&1 | tee -a "$RUN_LOG"
rc=${PIPESTATUS[0]}
set -e
exit "$rc"
