#!/usr/bin/env bash
set -euo pipefail

ROOT="${STRATEGY_DAILY_EOD_ROOT:-/Users/xiwei/stock_research}"
cd "$ROOT"

PYTHON_BIN="${STRATEGY_DAILY_EOD_PYTHON:-$ROOT/.venv/bin/python}"
TRADE_DATE="${STRATEGY_DAILY_EOD_TRADE_DATE:-${TRADE_DATE:-}}"
OUTPUT_ROOT="${STRATEGY_DAILY_EOD_OUTPUT_ROOT:-$ROOT/outputs/research/strategy_daily_eod}"
export STOCK_RESEARCH_RELEASE_ROOT="${STOCK_RESEARCH_RELEASE_ROOT:-$ROOT}"
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

# The daily pipeline writes ops.daily_pipeline_status during finalize (~21:00+).
# Earlier invocations would otherwise fail with "missing daily_pipeline_status"
# every trading day; poll while that is the only blocking reason and let real
# dependency failures (or probe errors, or timeout) fall through to the CLI,
# which reports them unchanged.
wait_for_daily_pipeline_status() {
  local max_seconds="$(( ${STRATEGY_DAILY_EOD_DEP_WAIT_MINUTES:-240} * 60 ))"
  local interval="${STRATEGY_DAILY_EOD_DEP_WAIT_INTERVAL_SECONDS:-300}"
  local waited=0
  local probe_rc
  local announced=0
  local last_stdout=0
  while true; do
    set +e
    PYTHONPATH=src "$PYTHON_BIN" - "$TRADE_DATE" >>"$DETAIL_LOG" 2>&1 <<'PY'
import sys
from stock_research.strategy_daily_eod import check_strategy_daily_eod_dependencies
result = check_strategy_daily_eod_dependencies(trade_date=sys.argv[1])
common = result.get("common") or {}
intraday = result.get("intraday") or {}
if common.get("status") == "success" and intraday.get("status") == "success":
    sys.exit(0)
reasons = f"{common.get('reason', '')}; {intraday.get('reason', '')}"
sys.exit(3 if "missing daily_pipeline_status" in reasons else 4)
PY
    probe_rc=$?
    set -e
    if [[ "$probe_rc" -eq 0 ]]; then
      echo "strategy_daily_eod|dependency_wait|ready|waited_seconds|$waited" >>"$DETAIL_LOG"
      return 0
    fi
    if [[ "$probe_rc" -ne 3 ]]; then
      echo "strategy_daily_eod|dependency_wait|probe_stop|rc|$probe_rc" >>"$DETAIL_LOG"
      return 0
    fi
    if (( waited >= max_seconds )); then
      echo "strategy_daily_eod|dependency_wait|timeout|waited_seconds|$waited" >>"$DETAIL_LOG"
      return 0
    fi
    if [[ "$announced" -eq 0 ]]; then
      announced=1
      echo "等待 daily_pipeline_status 就绪（最长 ${STRATEGY_DAILY_EOD_DEP_WAIT_MINUTES:-240} 分钟）..."
    fi
    sleep "$interval"
    waited=$((waited + interval))
    # sparse stdout heartbeat during the (up to 240min) dependency wait so the
    # OpenClaw no-output watchdog does not kill a healthy waiting job
    local stdout_interval="${STRATEGY_DAILY_EOD_STDOUT_HEARTBEAT_SECONDS:-600}"
    if (( waited - last_stdout >= stdout_interval )); then
      last_stdout=$waited
      echo "strategy_daily_eod|dependency_wait|heartbeat|waited_seconds|$waited"
    fi
  done
}

wait_for_daily_pipeline_status

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
  echo "日志: logs/${DETAIL_LOG##*/}"
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

ARTIFACT_SYNC_SCRIPT="$ROOT/deploy/sync_dashboard_artifacts.sh"
if [[ -x "$ARTIFACT_SYNC_SCRIPT" || -f "$ARTIFACT_SYNC_SCRIPT" ]]; then
  nohup /bin/bash "$ARTIFACT_SYNC_SCRIPT" >>"$LOG_DIR/dashboard_artifact_sync.trigger.log" 2>&1 &
  echo "已触发外网 artifact 同步（后台）: $ARTIFACT_SYNC_SCRIPT"
fi
