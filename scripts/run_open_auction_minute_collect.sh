#!/usr/bin/env bash
set -euo pipefail

ROOT="${OPEN_AUCTION_MINUTE_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${OPEN_AUCTION_MINUTE_PYTHON:-$ROOT/.venv/bin/python}"
TRADE_DATE="${1:-$(date +%F)}"
UNIVERSE_PATH="${OPEN_AUCTION_MINUTE_UNIVERSE_PATH:-$ROOT/outputs/research/open_auction_watch_universe_latest.csv}"
OUTPUT_DIR="${OPEN_AUCTION_MINUTE_OUTPUT_DIR:-$ROOT/outputs/research/open_auction_minute_collect}"
SLEEP_SECONDS="${OPEN_AUCTION_MINUTE_SLEEP_SECONDS:-0.2}"

MAX_SYMBOLS_ARG=()
if [ -n "${OPEN_AUCTION_MINUTE_MAX_SYMBOLS:-}" ]; then
  MAX_SYMBOLS_ARG=(--max-symbols "$OPEN_AUCTION_MINUTE_MAX_SYMBOLS")
fi

mkdir -p "$ROOT/logs"
cd "$ROOT"

"$PYTHON" -m stock_research.cli collect-open-auction-minute-v1 \
  --trade-date "$TRADE_DATE" \
  --universe-path "$UNIVERSE_PATH" \
  --start-time 09:15:00 \
  --end-time 09:25:00 \
  --sleep-seconds "$SLEEP_SECONDS" \
  "${MAX_SYMBOLS_ARG[@]}" \
  --output-dir "$OUTPUT_DIR"
