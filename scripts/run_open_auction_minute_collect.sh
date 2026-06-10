#!/usr/bin/env bash
set -euo pipefail

ROOT="${OPEN_AUCTION_MINUTE_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${OPEN_AUCTION_MINUTE_PYTHON:-$ROOT/.venv/bin/python}"
TRADE_DATE="${1:-$(date +%F)}"
UNIVERSE_PATH="${OPEN_AUCTION_MINUTE_UNIVERSE_PATH:-$ROOT/outputs/research/open_auction_watch_universe_latest.csv}"
OUTPUT_DIR="${OPEN_AUCTION_MINUTE_OUTPUT_DIR:-$ROOT/outputs/research/open_auction_minute_collect}"
SLEEP_SECONDS="${OPEN_AUCTION_MINUTE_SLEEP_SECONDS:-0.2}"
RETRY_UNTIL_COVERED="${OPEN_AUCTION_MINUTE_RETRY_UNTIL_COVERED:-0}"
MAX_ROUNDS="${OPEN_AUCTION_MINUTE_MAX_ROUNDS:-6}"
ROUND_SLEEP_SECONDS="${OPEN_AUCTION_MINUTE_ROUND_SLEEP_SECONDS:-300}"

mkdir -p "$ROOT/logs"
cd "$ROOT"

ARGS=(
  collect-open-auction-minute-v1
  --trade-date "$TRADE_DATE"
  --universe-path "$UNIVERSE_PATH"
  --start-time 09:15:00
  --end-time 09:25:00
  --sleep-seconds "$SLEEP_SECONDS"
  --output-dir "$OUTPUT_DIR"
)

if [ -n "${OPEN_AUCTION_MINUTE_MAX_SYMBOLS:-}" ]; then
  ARGS+=(--max-symbols "$OPEN_AUCTION_MINUTE_MAX_SYMBOLS")
fi

if [ "$RETRY_UNTIL_COVERED" = "1" ]; then
  ARGS+=(
    --retry-until-covered
    --max-rounds "$MAX_ROUNDS"
    --round-sleep-seconds "$ROUND_SLEEP_SECONDS"
  )
fi

"$PYTHON" -m stock_research.cli "${ARGS[@]}"
