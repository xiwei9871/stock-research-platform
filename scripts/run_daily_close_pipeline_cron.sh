#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
TRADE_DATE="${TRADE_DATE:-}"
STAGE="${1:-all}"
SMOKE_ONLY="${DAILY_CLOSE_SMOKE_ONLY:-0}"
HEARTBEAT_SECONDS="${DAILY_CLOSE_HEARTBEAT_SECONDS:-300}"
LOG_DIR="${DAILY_CLOSE_CRON_LOG_DIR:-$ROOT/logs/cron}"
RUN_TS="$(date '+%Y%m%d_%H%M%S')"
DETAIL_LOG="$LOG_DIR/daily_close_pipeline_${STAGE}_${TRADE_DATE:-auto}_${RUN_TS}.log"
mkdir -p "$LOG_DIR"

source "$ROOT/scripts/stock_cron_guard.sh"
clear_stock_proxy_env
stock_cron_guard_or_exit "$PYTHON_BIN" "$TRADE_DATE" "${RESEARCH_SERVICE:-}" >>"$DETAIL_LOG" 2>&1

if [[ "$SMOKE_ONLY" == "1" ]]; then
  echo "daily_close_pipeline|smoke|would_run|stage=${STAGE}|trade_date=${TRADE_DATE:-auto}"
  exit 0
fi

export DAILY_PIPELINE_CRON_OUTPUT="${DAILY_PIPELINE_CRON_OUTPUT:-compact}"

extract_json_value() {
  local key="$1"
  grep -E "\"${key}\"[[:space:]]*:" "$DETAIL_LOG" | tail -n 1 | sed -E 's/.*"'"$key"'"[[:space:]]*:[[:space:]]*"?([^",}]+)"?.*/\1/' || true
}

print_summary() {
  local title="$1"
  local rc="${2:-0}"
  echo "$title"
  echo "阶段: $STAGE"
  echo "交易日: ${TRADE_DATE:-auto}"
  local status
  local rows
  local expected
  local actual
  local missing
  status="$(extract_json_value status)"
  rows="$(extract_json_value rows)"
  expected="$(extract_json_value expected_count)"
  actual="$(extract_json_value actual_count)"
  missing="$(extract_json_value missing_count)"
  if [[ -n "$status" ]]; then
    echo "状态: $status"
  fi
  if [[ -n "$rows" ]]; then
    echo "入库行数: $rows"
  fi
  if [[ -n "$expected" || -n "$actual" || -n "$missing" ]]; then
    echo "覆盖: ${actual:-unknown}/${expected:-unknown}"
    echo "缺失: ${missing:-0}"
  fi
  if [[ "$rc" -ne 0 ]]; then
    echo "退出码: $rc"
  fi
  echo "详细日志: $DETAIL_LOG"
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

forward_signal() {
  if [[ -n "$PIPELINE_PID" ]]; then
    kill -TERM "$PIPELINE_PID" 2>/dev/null || true
  fi
}

trap forward_signal TERM INT
trap cleanup_heartbeat EXIT

echo "daily_close_pipeline|started|stage=${STAGE}|trade_date=${TRADE_DATE:-auto}|detail_log=${DETAIL_LOG}"

set +e
if [[ -n "${TRADE_DATE}" ]]; then
  "${PYTHON_BIN}" -m scripts.daily_pipeline --date "${TRADE_DATE}" --stage "${STAGE}" >>"$DETAIL_LOG" 2>&1 &
else
  "${PYTHON_BIN}" -m scripts.daily_pipeline --stage "${STAGE}" >>"$DETAIL_LOG" 2>&1 &
fi
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
    last_progress="$(grep -E '^(progress\|minute5_bar|minute5\|progress)' "$DETAIL_LOG" | tail -n 1 || true)"
    echo "daily_close_pipeline|heartbeat|stage=${STAGE}|trade_date=${TRADE_DATE:-auto}|elapsed_seconds=$((now_epoch-started_epoch))|last_progress=${last_progress:-waiting}"
  done
) &
HEARTBEAT_PID=$!

wait "$PIPELINE_PID"
rc=$?
set -e
cleanup_heartbeat

if [[ "$rc" -ne 0 ]]; then
  print_summary "股票日终阶段失败" "$rc"
  exit "$rc"
fi

if [[ "$STAGE" == "minute5" ]] && grep -Eq '"status"[[:space:]]*:[[:space:]]*"failed"' "$DETAIL_LOG"; then
  echo "daily_close_pipeline|business_failed|stage=minute5|trade_date=${TRADE_DATE:-auto}" >>"$DETAIL_LOG"
  print_summary "股票日终阶段失败" 1
  exit 1
fi

print_summary "股票日终阶段完成" 0
