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
  local lhb_status
  local mid_status
  local midtrend_artifacts_status
  local tech_status
  local dependency_common_status
  local dependency_intraday_status
  local dependency_reason
  status="$(grep -E '^strategy_daily_eod\|status\|' "$DETAIL_LOG" | tail -n 1 | awk -F'|' '{print $3}' || true)"
  review_rows="$(grep -E '^strategy_daily_eod\|review_rows\|' "$DETAIL_LOG" | tail -n 1 | awk -F'|' '{print $3}' || true)"
  lhb_status="$(grep -E '^strategy_daily_eod\|lhb_shortline_status\|' "$DETAIL_LOG" | tail -n 1 | awk -F'|' '{print $3}' || true)"
  mid_status="$(grep -E '^strategy_daily_eod\|mid_trend_status\|' "$DETAIL_LOG" | tail -n 1 | awk -F'|' '{print $3}' || true)"
  midtrend_artifacts_status="$(grep -E '^strategy_daily_eod\|strategy_midtrend_artifacts_status\|' "$DETAIL_LOG" | tail -n 1 | awk -F'|' '{print $3}' || true)"
  tech_status="$(grep -E '^strategy_daily_eod\|tech_bottleneck_status\|' "$DETAIL_LOG" | tail -n 1 | awk -F'|' '{print $3}' || true)"
  dependency_common_status="$(grep -E '^strategy_daily_eod\|dependency_common_status\|' "$DETAIL_LOG" | tail -n 1 | awk -F'|' '{print $3}' || true)"
  dependency_intraday_status="$(grep -E '^strategy_daily_eod\|dependency_intraday_status\|' "$DETAIL_LOG" | tail -n 1 | awk -F'|' '{print $3}' || true)"
  dependency_reason="$(grep -E '^strategy_daily_eod\|dependency_reason\|' "$DETAIL_LOG" | tail -n 1 | cut -d'|' -f3- || true)"
  if [[ -n "$status" ]]; then
    echo "状态: $status"
  fi
  if [[ -n "$review_rows" ]]; then
    echo "复盘条目: $review_rows"
  fi
  [[ -n "$lhb_status" ]] && echo "LHB: $lhb_status"
  [[ -n "$mid_status" ]] && echo "Mid Trend: $mid_status"
  [[ -n "$midtrend_artifacts_status" ]] && echo "Midtrend Artifacts: $midtrend_artifacts_status"
  [[ -n "$tech_status" ]] && echo "Tech Bottleneck: $tech_status"
  [[ -n "$dependency_common_status" ]] && echo "Common Dependency: $dependency_common_status"
  [[ -n "$dependency_intraday_status" ]] && echo "Intraday Dependency: $dependency_intraday_status"
  [[ -n "$dependency_reason" ]] && echo "依赖原因: $dependency_reason"
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
  if grep -q '^strategy_daily_eod|status|partial$' "$DETAIL_LOG"; then
    print_summary "策略日终部分完成" "$rc"
  else
    print_summary "策略日终失败" "$rc"
  fi
  exit "$rc"
fi

if grep -Eq '^strategy_daily_eod\|status\|(failed|partial)$' "$DETAIL_LOG"; then
  echo "strategy_daily_eod|business_failed|trade_date|${TRADE_DATE}" >>"$DETAIL_LOG"
  if grep -q '^strategy_daily_eod|status|partial$' "$DETAIL_LOG"; then
    print_summary "策略日终部分完成" 1
  else
    print_summary "策略日终失败" 1
  fi
  exit 1
fi

print_summary "策略日终完成" 0
