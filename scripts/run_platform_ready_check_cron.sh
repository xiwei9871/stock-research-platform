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

if [ -z "$TRADE_DATE" ]; then
  latest_market_date="$("$PYTHON" -c 'from stock_research.dashboard.platform import load_platform_summary; summary = load_platform_summary(); print(summary.get("latest_market_date") or summary.get("latest_trade_date") or "")' 2>/dev/null || true)"
  if [ -n "$latest_market_date" ]; then
    TRADE_DATE="$latest_market_date"
  else
    TRADE_DATE="$("$PYTHON" -c 'from stock_research.daily_close_pipeline import PipelineConfig, parse_trade_date; print(parse_trade_date(None, PipelineConfig().timezone).isoformat())')"
  fi
  REPAIR_OUTPUT_DIR="${PLATFORM_READY_REPAIR_OUTPUT_DIR:-$OUTPUT_DIR/eod_auto_repair/$TRADE_DATE}"
fi

DASHBOARD_AUTH_USERNAME="${DASHBOARD_AUTH_USERNAME:-eod_repair}"
DASHBOARD_AUTH_PASSWORD="${DASHBOARD_AUTH_PASSWORD:-}"
DASHBOARD_AUTH_KEYCHAIN_SERVICE="${DASHBOARD_AUTH_KEYCHAIN_SERVICE:-stock-research-dashboard-eod-repair}"

mkdir -p "$LOG_DIR" "$OUTPUT_DIR" "$REPAIR_OUTPUT_DIR" "$(dirname "$RUN_LOG")"

source "$ROOT/scripts/stock_cron_guard.sh"
source "$ROOT/scripts/repair_publication_lock.sh"
clear_stock_proxy_env

if [[ -z "$DASHBOARD_AUTH_PASSWORD" ]] && command -v security >/dev/null 2>&1; then
  DASHBOARD_AUTH_PASSWORD="$(
    security find-generic-password \
      -s "$DASHBOARD_AUTH_KEYCHAIN_SERVICE" \
      -a "$DASHBOARD_AUTH_USERNAME" \
      -w 2>/dev/null || true
  )"
fi
export DASHBOARD_AUTH_PASSWORD

stock_cron_guard_or_exit "$PYTHON" "$TRADE_DATE" "${RESEARCH_SERVICE:-}" >>"$RUN_LOG" 2>&1

print_summary() {
  local title="$1"
  local rc="$2"
  echo "$title"
  echo "交易日: $TRADE_DATE"
  echo "摘要文件: $REPAIR_OUTPUT_DIR/run_summary.json"
  echo "报告文件: $REPAIR_OUTPUT_DIR/run_report.md"
  if [ "$rc" -ne 0 ]; then
    echo "退出码: $rc"
  fi
  echo "详细日志: $RUN_LOG"
}

PIPELINE_PID=""
HEARTBEAT_PID=""

cleanup_heartbeat() {
  if [[ -n "$HEARTBEAT_PID" ]]; then
    kill "$HEARTBEAT_PID" 2>/dev/null || true
    wait "$HEARTBEAT_PID" 2>/dev/null || true
    HEARTBEAT_PID=""
  fi
}

cleanup_all() {
  cleanup_heartbeat
  release_repair_publication_lock
}

finalize_publication() {
  local repair_rc="$1"
  "$PYTHON" -m stock_research.eod_auto_repair \
    --finalize-publication \
    --trade-date "$TRADE_DATE" \
    --output-dir "$REPAIR_OUTPUT_DIR" \
    --release-root "$ROOT" \
    --publication-mode publish_if_missing \
    --repair-exit-code "$repair_rc" >>"$RUN_LOG" 2>&1
}

forward_signal() {
  if [[ -n "$PIPELINE_PID" ]]; then
    kill -TERM "$PIPELINE_PID" 2>/dev/null || true
  fi
}

trap forward_signal TERM INT
trap cleanup_all EXIT

if ! acquire_repair_publication_lock "$ROOT"; then
  echo "platform_ready_check|locked|trade_date=${TRADE_DATE}"
  exit 0
fi

echo "platform_ready_check|started|stage=eod_auto_repair|trade_date=${TRADE_DATE}|detail_log=${RUN_LOG}"
echo "=== eod auto repair start: $(date '+%Y-%m-%d %H:%M:%S %z') ===" >>"$RUN_LOG"
RUN_LOG_START_LINE="$(($(wc -l < "$RUN_LOG") + 1))"
cd "$ROOT"

"$PYTHON" -m stock_research.eod_auto_repair \
  --trade-date "$TRADE_DATE" \
  --output-dir "$REPAIR_OUTPUT_DIR" \
  --mode repair >>"$RUN_LOG" 2>&1 &
PIPELINE_PID=$!

(
  HEARTBEAT_SLEEP_PID=""
  stop_heartbeat_loop() {
    if [[ -n "$HEARTBEAT_SLEEP_PID" ]]; then
      kill "$HEARTBEAT_SLEEP_PID" 2>/dev/null || true
    fi
    exit 0
  }
  trap stop_heartbeat_loop TERM INT
  started_epoch="$(date +%s)"
  while kill -0 "$PIPELINE_PID" 2>/dev/null; do
    sleep "$HEARTBEAT_SECONDS" &
    HEARTBEAT_SLEEP_PID=$!
    wait "$HEARTBEAT_SLEEP_PID" || exit 0
    HEARTBEAT_SLEEP_PID=""
    kill -0 "$PIPELINE_PID" 2>/dev/null || break
    now_epoch="$(date +%s)"
    last_progress="$(tail -n +"$RUN_LOG_START_LINE" "$RUN_LOG" | grep -E '^(eod_auto_repair\||progress\||free_enrichment_batch\|)' | tail -n 1 || true)"
    echo "platform_ready_check|heartbeat|stage=eod_auto_repair|trade_date=${TRADE_DATE}|elapsed_seconds=$((now_epoch-started_epoch))|last_progress=${last_progress:-waiting}"
  done
) &
HEARTBEAT_PID=$!

set +e
wait "$PIPELINE_PID"
rc=$?
set -e
cleanup_heartbeat

echo "eod_auto_repair|summary|$REPAIR_OUTPUT_DIR/run_summary.json" >>"$RUN_LOG"
echo "eod_auto_repair|report|$REPAIR_OUTPUT_DIR/run_report.md" >>"$RUN_LOG"
echo "=== eod auto repair end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ===" >>"$RUN_LOG"
repair_rc=$rc
set +e
finalize_publication "$repair_rc"
rc=$?
set -e
if [ "$rc" -ne 0 ]; then
  if [ "$repair_rc" -ne 0 ]; then
    print_summary "EOD自动修复失败" "$rc"
  else
    print_summary "EOD自动修复发布失败" "$rc"
  fi
else
  print_summary "EOD自动修复完成" "$rc"
fi
exit "$rc"
