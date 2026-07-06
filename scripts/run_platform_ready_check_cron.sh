#!/usr/bin/env bash
set -euo pipefail

ROOT="${PLATFORM_READY_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${PLATFORM_READY_PYTHON:-$ROOT/.venv/bin/python}"
LOG_DIR="${PLATFORM_READY_LOG_DIR:-$ROOT/logs}"
RUN_LOG="${PLATFORM_READY_CHECK_RUN_LOG:-$LOG_DIR/platform_ready_check.host.log}"
TRADE_DATE="${PLATFORM_READY_TRADE_DATE:-}"
REPORTS_DIR="${PLATFORM_READY_REPORTS_DIR:-$ROOT/reports}"
OUTPUT_DIR="${PLATFORM_READY_OUTPUT_DIR:-$ROOT/outputs/research}"
REPAIR_OUTPUT_DIR="${PLATFORM_READY_REPAIR_OUTPUT_DIR:-$OUTPUT_DIR/eod_auto_repair/$TRADE_DATE}"
HEARTBEAT_SECONDS="${PLATFORM_READY_CHECK_HEARTBEAT_SECONDS:-60}"

source "$ROOT/scripts/stock_cron_guard.sh"
clear_stock_proxy_env

if [ -z "$TRADE_DATE" ]; then
  latest_market_date="$("$PYTHON" -c 'from stock_research.dashboard.platform import load_platform_summary; summary = load_platform_summary(); print(summary.get("latest_market_date") or summary.get("latest_trade_date") or "")' 2>/dev/null || true)"
  if [ -n "$latest_market_date" ]; then
    TRADE_DATE="$latest_market_date"
  else
    TRADE_DATE="$("$PYTHON" -c 'from stock_research.daily_close_pipeline import PipelineConfig, parse_trade_date; print(parse_trade_date(None, PipelineConfig().timezone).isoformat())')"
  fi
  REPAIR_OUTPUT_DIR="${PLATFORM_READY_REPAIR_OUTPUT_DIR:-$OUTPUT_DIR/eod_auto_repair/$TRADE_DATE}"
fi

stock_cron_guard_or_exit "$PYTHON" "$TRADE_DATE" "${RESEARCH_SERVICE:-}"

mkdir -p "$LOG_DIR" "$OUTPUT_DIR" "$(dirname "$RUN_LOG")"

run_with_heartbeat() {
  local stage="$1"
  shift
  local started
  local elapsed
  local next_heartbeat
  local pid
  started="$(date +%s)"
  next_heartbeat="$HEARTBEAT_SECONDS"
  "$@" &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    sleep 1
    elapsed=$(($(date +%s) - started))
    if kill -0 "$pid" 2>/dev/null; then
      if [ "$elapsed" -ge "$next_heartbeat" ]; then
        echo "platform_ready_check|stage|${stage}|heartbeat|elapsed=${elapsed}"
        next_heartbeat=$((next_heartbeat + HEARTBEAT_SECONDS))
      fi
    fi
  done
  wait "$pid"
}

set +e
{
  echo "=== eod auto repair start: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
  cd "$ROOT"
  run_with_heartbeat eod_auto_repair rtk "$PYTHON" -m stock_research.eod_auto_repair \
    --trade-date "$TRADE_DATE" \
    --output-dir "$REPAIR_OUTPUT_DIR" \
    --mode repair
  rc=$?
  echo "eod_auto_repair|summary|$REPAIR_OUTPUT_DIR/run_summary.json"
  echo "eod_auto_repair|report|$REPAIR_OUTPUT_DIR/run_report.md"
  echo "=== eod auto repair end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ==="
  exit "$rc"
} 2>&1 | tee -a "$RUN_LOG"
rc=${PIPESTATUS[0]}
set -e
exit "$rc"
