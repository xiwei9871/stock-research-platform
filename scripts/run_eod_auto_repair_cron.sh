#!/usr/bin/env bash
set -euo pipefail

ROOT="${STOCK_RESEARCH_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${STOCK_RESEARCH_PYTHON:-$ROOT/.venv/bin/python}"
TRADE_DATE="${1:-$(date +%F)}"
LOG_DIR="$ROOT/logs/eod_auto_repair"
OUTPUT_DIR="$ROOT/outputs/research/eod_auto_repair/$TRADE_DATE"
LOCK_FILE="$ROOT/.locks/eod_auto_repair.lock"

source "$ROOT/scripts/stock_cron_guard.sh"
clear_stock_proxy_env

mkdir -p "$LOG_DIR" "$OUTPUT_DIR" "$(dirname "$LOCK_FILE")"

acquire_lock() {
  while true; do
    if mkdir "$LOCK_FILE" 2>/dev/null; then
      printf '%s\n' "$$" > "$LOCK_FILE/pid"
      trap 'rm -rf "$LOCK_FILE"' EXIT INT TERM
      return 0
    fi

    if [[ -d "$LOCK_FILE" ]]; then
      return 1
    fi

    lock_pid="$(cat "$LOCK_FILE" 2>/dev/null || true)"
    if ! [[ "$lock_pid" =~ ^[0-9]+$ ]]; then
      return 1
    fi
    if kill -0 "$lock_pid" 2>/dev/null; then
      return 1
    fi

    rm -f "$LOCK_FILE" 2>/dev/null || true
  done
}

if ! acquire_lock; then
  echo "eod_auto_repair|locked|$LOCK_FILE" | tee -a "$LOG_DIR/$TRADE_DATE.log"
  exit 0
fi

cd "$ROOT"
set +e
{
  echo "=== eod auto repair start: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
  # Entrypoint: python -m stock_research.eod_auto_repair
  rtk "$PYTHON" -m stock_research.eod_auto_repair \
    --trade-date "$TRADE_DATE" \
    --output-dir "$OUTPUT_DIR" \
    --mode repair
  rc=$?
  echo "eod_auto_repair|summary|$OUTPUT_DIR/run_summary.json"
  echo "eod_auto_repair|report|$OUTPUT_DIR/run_report.md"
  echo "=== eod auto repair end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ==="
  exit "$rc"
} 2>&1 | tee -a "$LOG_DIR/$TRADE_DATE.log"
rc=${PIPESTATUS[0]}
set -e
exit "$rc"
