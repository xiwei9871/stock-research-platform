#!/usr/bin/env bash
set -euo pipefail

ROOT="${STRATEGY_DAILY_EOD_ROOT:-/Users/xiwei/stock_research}"
cd "$ROOT"

PYTHON_BIN="${STRATEGY_DAILY_EOD_PYTHON:-$ROOT/.venv/bin/python}"
TRADE_DATE="${STRATEGY_DAILY_EOD_TRADE_DATE:-${TRADE_DATE:-}}"
OUTPUT_ROOT="${STRATEGY_DAILY_EOD_OUTPUT_ROOT:-$ROOT/outputs/research/strategy_daily_eod}"
LOG_DIR="${STRATEGY_DAILY_EOD_LOG_DIR:-$ROOT/logs/cron}"
RUN_TS="$(date '+%Y%m%d_%H%M%S')"
DETAIL_LOG="$LOG_DIR/strategy_daily_eod_${TRADE_DATE:-auto}_${RUN_TS}.log"
mkdir -p "$LOG_DIR"

source "$ROOT/scripts/stock_cron_guard.sh"
clear_stock_proxy_env
stock_cron_guard_or_exit "$PYTHON_BIN" "$TRADE_DATE" "${RESEARCH_SERVICE:-}" >>"$DETAIL_LOG" 2>&1

if [[ -z "${TRADE_DATE}" ]]; then
  TRADE_DATE="$("$PYTHON_BIN" -c 'from datetime import date; print(date.today().isoformat())')"
fi

print_summary() {
  local title="$1"
  local rc="$2"
  echo "$title"
  echo "交易日: $TRADE_DATE"
  local status
  local review_rows
  status="$(grep -E '^strategy_daily_eod\|status\|' "$DETAIL_LOG" | tail -n 1 | awk -F'|' '{print $3}' || true)"
  review_rows="$(grep -E '^strategy_daily_eod\|review_rows\|' "$DETAIL_LOG" | tail -n 1 | awk -F'|' '{print $3}' || true)"
  if [[ -n "$status" ]]; then
    echo "状态: $status"
  fi
  if [[ -n "$review_rows" ]]; then
    echo "复盘条目: $review_rows"
  fi
  if [[ "$rc" -ne 0 ]]; then
    echo "退出码: $rc"
  fi
  echo "详细日志: $DETAIL_LOG"
}

set +e
PYTHONPATH=src "$PYTHON_BIN" -m stock_research.cli run-strategy-daily-eod \
  --trade-date "$TRADE_DATE" \
  --output-root "$OUTPUT_ROOT" >>"$DETAIL_LOG" 2>&1
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  print_summary "策略日终失败" "$rc"
  exit "$rc"
fi

if grep -q '^strategy_daily_eod|status|failed$' "$DETAIL_LOG"; then
  echo "strategy_daily_eod|business_failed|trade_date|${TRADE_DATE}" >>"$DETAIL_LOG"
  print_summary "策略日终失败" 1
  exit 1
fi

print_summary "策略日终完成" 0
