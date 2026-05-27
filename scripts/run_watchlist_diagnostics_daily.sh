#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/xiwei/stock_research"
PYTHON="$ROOT/.venv/bin/python"
CLI="$PYTHON -m stock_research.cli"
OUTPUT_DIR="$ROOT/outputs/research"

TRADE_DATE="${1:-}"
REVIEW_DAYS="${REVIEW_DAYS:-20}"

if [ -z "$TRADE_DATE" ]; then
  echo "usage: $0 YYYY-MM-DD" >&2
  exit 1
fi

REVIEW_START_DATE="$("$PYTHON" - <<PY
from datetime import date, timedelta
trade_date = date.fromisoformat("$TRADE_DATE")
print((trade_date - timedelta(days=int("$REVIEW_DAYS") * 2)).isoformat())
PY
)"

cd "$ROOT"

$CLI build-watchlist-diagnostics \
  --trade-date "$TRADE_DATE" \
  --score-version manual_v1 \
  --top-n 50 \
  --risk-watch-n 10 \
  --opportunity-watch-n 10 \
  --output-dir "$OUTPUT_DIR"

$CLI review-watchlist-diagnostics \
  --diagnostics-dir "$OUTPUT_DIR" \
  --start-date "$REVIEW_START_DATE" \
  --end-date "$TRADE_DATE" \
  --output-dir "$OUTPUT_DIR"

echo "watchlist_runbook|trade_date|$TRADE_DATE"
echo "watchlist_runbook|review_start_date|$REVIEW_START_DATE"
echo "watchlist_runbook|diagnostics_markdown|$OUTPUT_DIR/watchlist_diagnostics_${TRADE_DATE}_diagnostics_v1.md"
