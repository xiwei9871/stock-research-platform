#!/usr/bin/env bash
set -euo pipefail

ROOT="${OPEN_AUCTION_SPOT_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${OPEN_AUCTION_SPOT_PYTHON:-$ROOT/.venv/bin/python}"
TRADE_DATE="${1:-$(date +%F)}"
OUTPUT_DIR="${OPEN_AUCTION_SPOT_OUTPUT_DIR:-$ROOT/outputs/research/open_auction_spot_snapshot}"
LOCK_DIR="${OPEN_AUCTION_SPOT_LOCK_DIR:-$ROOT/tmp/open_auction_spot_snapshot_day.lock}"

mkdir -p "$ROOT/tmp" "$ROOT/logs"

acquire_lock() {
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "$$" > "$LOCK_DIR/pid"
    return 0
  fi

  local lock_pid=""
  if [[ -f "$LOCK_DIR/pid" ]]; then
    lock_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  fi
  if [[ -n "$lock_pid" ]] && ! kill -0 "$lock_pid" 2>/dev/null; then
    rm -f "$LOCK_DIR/pid"
    rmdir "$LOCK_DIR" 2>/dev/null || true
    if mkdir "$LOCK_DIR" 2>/dev/null; then
      echo "$$" > "$LOCK_DIR/pid"
      echo "open_auction_spot_snapshot_day|stale_lock_recovered|trade_date|$TRADE_DATE|lock_dir|$LOCK_DIR|pid|$lock_pid"
      return 0
    fi
  fi

  echo "open_auction_spot_snapshot_day|locked|trade_date|$TRADE_DATE|lock_dir|$LOCK_DIR|pid|$lock_pid"
  return 1
}

if ! acquire_lock; then
  exit 0
fi

cleanup() {
  rm -f "$LOCK_DIR/pid"
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT

cd "$ROOT"

TRADING_STATUS="$("$PYTHON" - "$TRADE_DATE" <<'PY'
import sys

from stock_research.auction_data import open_trading_date_status

print(open_trading_date_status(sys.argv[1]))
PY
)"

if [[ "$TRADING_STATUS" == "closed" ]]; then
  echo "open_auction_spot_snapshot_day|skip_closed|trade_date|$TRADE_DATE"
  exit 0
fi

echo "open_auction_spot_snapshot_day|start|trade_date|$TRADE_DATE|status|$TRADING_STATUS"

FAILED=0

wait_until() {
  local trigger_time="$1"
  "$PYTHON" - "$trigger_time" <<'PY'
import sys
import time
from datetime import datetime

trigger_time = datetime.strptime(sys.argv[1], "%H:%M:%S").time()
target = datetime.combine(datetime.now().date(), trigger_time)
seconds = max(0.0, (target - datetime.now()).total_seconds())
if seconds:
    print(f"open_auction_spot_snapshot_day|wait|trigger|{sys.argv[1]}|seconds|{seconds:.1f}", flush=True)
    time.sleep(seconds)
PY
}

collect_target() {
  local target_time="$1"
  local trigger_time="$2"
  wait_until "$trigger_time"
  echo "open_auction_spot_snapshot_day|collect_start|target_time|$target_time|trigger_time|$trigger_time|at|$(date '+%F %T')"
  if OPEN_AUCTION_SPOT_OUTPUT_DIR="$OUTPUT_DIR" scripts/run_open_auction_spot_snapshot.sh "$target_time" "$TRADE_DATE"; then
    echo "open_auction_spot_snapshot_day|collect_done|target_time|$target_time|at|$(date '+%F %T')"
  else
    FAILED=1
    echo "open_auction_spot_snapshot_day|collect_failed|target_time|$target_time|at|$(date '+%F %T')"
  fi
}

collect_target "09:15" "09:15:05"
collect_target "09:17" "09:17:05"
collect_target "09:19" "09:19:05"
collect_target "09:21" "09:21:05"
collect_target "09:23" "09:23:05"
collect_target "09:25" "09:25:10"

if [[ "$FAILED" -eq 0 ]]; then
  echo "open_auction_spot_snapshot_day|done|trade_date|$TRADE_DATE|status|success"
else
  echo "open_auction_spot_snapshot_day|done|trade_date|$TRADE_DATE|status|failed"
fi
exit "$FAILED"
