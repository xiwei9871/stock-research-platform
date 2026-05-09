#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/xiwei/stock_research"
PYTHON="$ROOT/.venv/bin/python"
LOG_DIR="$ROOT/logs"
TODAY="$(date +%Y%m%d)"
LOG_PATH="$LOG_DIR/research_$TODAY.log"

mkdir -p "$LOG_DIR"

{
  echo "=== stock research start: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
  cd "$ROOT"

  "$PYTHON" -m stock_research.cli apply-schema
  "$PYTHON" -m stock_research.cli sync-assets

  TRADE_DATE="$("$PYTHON" - <<'PY'
from stock_research.market_data import latest_source_trade_date

print(latest_source_trade_date("stock_hfq") or "")
PY
)"

  if [ -z "$TRADE_DATE" ]; then
    echo "research_failed|no_trade_date"
    exit 1
  fi

  START_DATE="$("$PYTHON" - <<PY
from datetime import date, timedelta

trade_date = date.fromisoformat("$TRADE_DATE")
print((trade_date - timedelta(days=140)).isoformat())
PY
)"

  "$PYTHON" -m stock_research.cli load-bars --start-date "$START_DATE" --end-date "$TRADE_DATE"
  "$PYTHON" -m stock_research.cli quality --trade-date "$TRADE_DATE"
  "$PYTHON" -m stock_research.cli features --trade-date "$TRADE_DATE"
  "$PYTHON" -m stock_research.cli labels --end-date "$TRADE_DATE"
  "$PYTHON" -m stock_research.cli select --trade-date "$TRADE_DATE" --top-n 20
  "$PYTHON" -m stock_research.cli report --trade-date "$TRADE_DATE" --log-path "$LOG_PATH"

  echo "=== stock research ok: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
} 2>&1 | tee "$LOG_PATH"
