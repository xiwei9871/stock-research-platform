#!/usr/bin/env bash
set -euo pipefail

ROOT="${STOCK_RESEARCH_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${STOCK_RESEARCH_PYTHON:-$ROOT/.venv/bin/python}"
TRADE_DATE="${1:-$(date +%F)}"
LOG_DIR="$ROOT/logs/eod_auto_repair"
OUTPUT_DIR="$ROOT/outputs/research/eod_auto_repair/$TRADE_DATE"
DETAIL_LOG="$LOG_DIR/$TRADE_DATE.log"
ACTION_TIMEOUT_SECONDS="${EOD_AUTO_REPAIR_ACTION_TIMEOUT_SECONDS:-43200}"
DASHBOARD_AUTH_USERNAME="${DASHBOARD_AUTH_USERNAME:-eod_repair}"
DASHBOARD_AUTH_PASSWORD="${DASHBOARD_AUTH_PASSWORD:-}"
DASHBOARD_AUTH_KEYCHAIN_SERVICE="${DASHBOARD_AUTH_KEYCHAIN_SERVICE:-stock-research-dashboard-eod-repair}"

source "$ROOT/scripts/stock_cron_guard.sh"
source "$ROOT/scripts/repair_publication_lock.sh"
clear_stock_proxy_env

mkdir -p "$LOG_DIR" "$OUTPUT_DIR" "$ROOT/.locks"

if [[ -z "$DASHBOARD_AUTH_PASSWORD" ]] && command -v security >/dev/null 2>&1; then
  DASHBOARD_AUTH_PASSWORD="$(
    security find-generic-password \
      -s "$DASHBOARD_AUTH_KEYCHAIN_SERVICE" \
      -a "$DASHBOARD_AUTH_USERNAME" \
      -w 2>/dev/null || true
  )"
fi
export DASHBOARD_AUTH_PASSWORD

log_locked() {
  echo "eod_auto_repair|locked|lock_mode|${REPAIR_PUBLICATION_LOCK_MODE:-unknown}" >>"$DETAIL_LOG"
  echo "EOD自动修复跳过"
  echo "交易日: $TRADE_DATE"
  echo "原因: 已有任务运行"
  echo "锁模式: ${REPAIR_PUBLICATION_LOCK_MODE:-unknown}"
  echo "详细日志: $DETAIL_LOG"
}

finalize_publication() {
  local repair_rc="$1"
  rtk "$PYTHON" -m stock_research.eod_auto_repair \
    --finalize-publication \
    --trade-date "$TRADE_DATE" \
    --output-dir "$OUTPUT_DIR" \
    --release-root "$ROOT" \
    --publication-mode require_existing \
    --repair-exit-code "$repair_rc" >>"$DETAIL_LOG" 2>&1
}

print_summary() {
  local title="$1"
  local rc="$2"
  echo "$title"
  echo "交易日: $TRADE_DATE"
  echo "锁模式: $LOCK_MODE"
  echo "摘要文件: $OUTPUT_DIR/run_summary.json"
  echo "报告文件: $OUTPUT_DIR/run_report.md"
  if [[ "$rc" -ne 0 ]]; then
    echo "退出码: $rc"
  fi
  echo "详细日志: $DETAIL_LOG"
}

run_repair() {
  cd "$ROOT"
  set +e
  echo "=== eod auto repair start: $(date '+%Y-%m-%d %H:%M:%S %z') ===" >>"$DETAIL_LOG"
  echo "eod_auto_repair|lock_mode|$LOCK_MODE" >>"$DETAIL_LOG"
  # Entrypoint: python -m stock_research.eod_auto_repair
  rtk "$PYTHON" -m stock_research.eod_auto_repair \
    --trade-date "$TRADE_DATE" \
    --output-dir "$OUTPUT_DIR" \
    --mode loop \
    --action-timeout-seconds "$ACTION_TIMEOUT_SECONDS" >>"$DETAIL_LOG" 2>&1 &
  PIPELINE_PID=$!
  wait "$PIPELINE_PID"
  rc=$?
  PIPELINE_PID=""
  echo "eod_auto_repair|summary|$OUTPUT_DIR/run_summary.json" >>"$DETAIL_LOG"
  echo "eod_auto_repair|report|$OUTPUT_DIR/run_report.md" >>"$DETAIL_LOG"
  if [[ "$INTERRUPTED" -eq 0 ]]; then
    repair_rc=$rc
    finalize_publication "$repair_rc"
    rc=$?
  fi
  echo "=== eod auto repair end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ===" >>"$DETAIL_LOG"
  set -e
  if [[ "$rc" -ne 0 ]]; then
    print_summary "EOD自动修复失败" "$rc"
  else
    print_summary "EOD自动修复完成" "$rc"
  fi
  return "$rc"
}

PIPELINE_PID=""
INTERRUPTED=0
forward_signal() {
  INTERRUPTED=1
  if [[ -n "$PIPELINE_PID" ]]; then
    kill -TERM "$PIPELINE_PID" 2>/dev/null || true
  fi
}
cleanup() {
  release_repair_publication_lock
}
trap forward_signal TERM INT
trap cleanup EXIT

if ! acquire_repair_publication_lock "$ROOT"; then
  log_locked
  exit 75
fi
LOCK_MODE="$REPAIR_PUBLICATION_LOCK_MODE"

run_repair
exit "$?"
