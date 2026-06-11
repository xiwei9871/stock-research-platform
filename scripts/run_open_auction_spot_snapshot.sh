#!/usr/bin/env bash
set -euo pipefail

ROOT="${OPEN_AUCTION_SPOT_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${OPEN_AUCTION_SPOT_PYTHON:-$ROOT/.venv/bin/python}"
TARGET_TIME="${1:?target time is required, for example 09:17}"
TRADE_DATE="${2:-$(date +%F)}"
OUTPUT_DIR="${OPEN_AUCTION_SPOT_OUTPUT_DIR:-$ROOT/outputs/research/open_auction_spot_snapshot}"

mkdir -p "$ROOT/logs"
cd "$ROOT"

"$PYTHON" -m stock_research.cli collect-open-auction-spot-snapshot-v1 \
  --trade-date "$TRADE_DATE" \
  --target-time "$TARGET_TIME" \
  --output-dir "$OUTPUT_DIR"
