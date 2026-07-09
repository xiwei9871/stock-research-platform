#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
TRADE_DATE="${TRADE_DATE:-}"
DASHBOARD_CACHE_CLEAR_URL="${DASHBOARD_CACHE_CLEAR_URL:-http://127.0.0.1:8765/api/dashboard/cache/clear}"
SMOKE_ONLY="${DAILY_CLOSE_SMOKE_ONLY:-0}"
LOG_DIR="${DAILY_CLOSE_CRON_LOG_DIR:-$ROOT/logs/cron}"
RUN_TS="$(date '+%Y%m%d_%H%M%S')"
DETAIL_LOG="$LOG_DIR/daily_close_finalize_${TRADE_DATE:-auto}_${RUN_TS}.log"
mkdir -p "$LOG_DIR"

source "$ROOT/scripts/stock_cron_guard.sh"
clear_stock_proxy_env
stock_cron_guard_or_exit "$PYTHON_BIN" "$TRADE_DATE" "${RESEARCH_SERVICE:-}" >>"$DETAIL_LOG" 2>&1

if [[ "$SMOKE_ONLY" == "1" ]]; then
  for stage in retry_failed market_monitor deps health; do
    echo "daily_close_finalize|smoke|would_run|stage=${stage}|trade_date=${TRADE_DATE:-auto}"
  done
  echo "daily_close_finalize|smoke|would_run|dashboard_cache_clear|url=${DASHBOARD_CACHE_CLEAR_URL:-}"
  exit 0
fi

resolve_args=()
if [[ -n "${TRADE_DATE}" ]]; then
  resolve_args+=(--date "${TRADE_DATE}")
fi

retry_failed_status="pending"
market_monitor_status="pending"
deps_status="pending"
health_status="pending"
dashboard_cache_status="pending"
failed_stage=""
failed_rc=0

set_stage_status() {
  local stage="$1"
  local status="$2"
  case "$stage" in
    retry_failed) retry_failed_status="$status" ;;
    market_monitor) market_monitor_status="$status" ;;
    deps) deps_status="$status" ;;
    health) health_status="$status" ;;
  esac
}

stage_status_summary() {
  printf 'retry_failed=%s, market_monitor=%s, deps=%s, health=%s' \
    "$retry_failed_status" "$market_monitor_status" "$deps_status" "$health_status"
}

extract_json_value() {
  local key="$1"
  grep -E "\"${key}\"[[:space:]]*:" "$DETAIL_LOG" | tail -n 1 | sed -E 's/.*"'"$key"'"[[:space:]]*:[[:space:]]*"?([^",}]+)"?.*/\1/' || true
}

print_summary() {
  local title="$1"
  echo "$title"
  echo "交易日: ${TRADE_DATE:-auto}"
  echo "阶段: $(stage_status_summary)"
  if [[ -n "${failed_stage:-}" ]]; then
    echo "失败阶段: $failed_stage"
    echo "退出码: $failed_rc"
  fi
  local pipeline_status
  local minute5_status
  pipeline_status="$(extract_json_value pipeline_status)"
  minute5_status="$(extract_json_value minute5_status)"
  if [[ -n "$pipeline_status" ]]; then
    echo "平台状态: $pipeline_status"
  fi
  if [[ -n "$minute5_status" ]]; then
    echo "5分钟线: $minute5_status"
  fi
  echo "Dashboard缓存: $dashboard_cache_status"
  echo "详细日志: $DETAIL_LOG"
}

run_stage_command() {
  local stage="$1"
  shift
  local timeout_seconds="${FINALIZE_STAGE_TIMEOUT_SECONDS:-2700}"

  if [[ ! "$timeout_seconds" =~ ^[0-9]+$ ]] || [[ "$timeout_seconds" -le 0 ]]; then
    "$@" >>"$DETAIL_LOG" 2>&1
    return $?
  fi

  "$@" >>"$DETAIL_LOG" 2>&1 &
  local child_pid=$!
  local elapsed=0
  local heartbeat_seconds="${FINALIZE_STAGE_HEARTBEAT_SECONDS:-60}"
  if [[ ! "$heartbeat_seconds" =~ ^[0-9]+$ ]] || [[ "$heartbeat_seconds" -le 0 ]]; then
    heartbeat_seconds=0
  fi
  while kill -0 "$child_pid" 2>/dev/null; do
    if [[ "$elapsed" -ge "$timeout_seconds" ]]; then
      echo "daily_close_finalize|stage|${stage}|timeout|${timeout_seconds}" >>"$DETAIL_LOG"
      {
        kill -TERM "$child_pid" 2>/dev/null || true
        sleep 2
        kill -KILL "$child_pid" 2>/dev/null || true
        wait "$child_pid" 2>/dev/null || true
      } 2>>"$DETAIL_LOG"
      return 124
    fi
    sleep 1
    elapsed=$((elapsed + 1))
    if [[ "$heartbeat_seconds" -gt 0 && $((elapsed % heartbeat_seconds)) -eq 0 ]]; then
      echo "daily_close_finalize|stage|${stage}|heartbeat|elapsed=${elapsed}" >>"$DETAIL_LOG"
    fi
  done
  wait "$child_pid"
}

run_stage() {
  local stage="$1"
  echo "daily_close_finalize|stage|${stage}|start|$(date '+%Y-%m-%d %H:%M:%S %z')" >>"$DETAIL_LOG"
  local rc=0
  set +e
  if [[ -n "${TRADE_DATE}" ]]; then
    DAILY_PIPELINE_CRON_OUTPUT=compact run_stage_command "${stage}" "${PYTHON_BIN}" -m scripts.daily_pipeline --date "${TRADE_DATE}" --stage "${stage}"
    rc=$?
  else
    DAILY_PIPELINE_CRON_OUTPUT=compact run_stage_command "${stage}" "${PYTHON_BIN}" -m scripts.daily_pipeline --stage "${stage}"
    rc=$?
  fi
  if [[ "$rc" -ne 0 ]]; then
    echo "daily_close_finalize|stage|${stage}|failed|rc=${rc}|$(date '+%Y-%m-%d %H:%M:%S %z')" >>"$DETAIL_LOG"
    set_stage_status "$stage" "failed(rc=${rc})"
    return "$rc"
  fi
  set -e
  set_stage_status "$stage" "success"
  echo "daily_close_finalize|stage|${stage}|done|$(date '+%Y-%m-%d %H:%M:%S %z')" >>"$DETAIL_LOG"
}

clear_dashboard_cache() {
  if [[ -z "${DASHBOARD_CACHE_CLEAR_URL:-}" ]]; then
    dashboard_cache_status="skipped(url_empty)"
    echo "daily_close_finalize|dashboard_cache_clear|skipped|url_empty" >>"$DETAIL_LOG"
    return 0
  fi
  if ! command -v curl >/dev/null 2>&1; then
    dashboard_cache_status="skipped(curl_missing)"
    echo "daily_close_finalize|dashboard_cache_clear|skipped|curl_missing|url|$DASHBOARD_CACHE_CLEAR_URL" >>"$DETAIL_LOG"
    return 0
  fi
  if curl -fsS -m 5 -X POST "$DASHBOARD_CACHE_CLEAR_URL" >>"$DETAIL_LOG" 2>&1; then
    dashboard_cache_status="success"
    echo "daily_close_finalize|dashboard_cache_clear|success|url|$DASHBOARD_CACHE_CLEAR_URL" >>"$DETAIL_LOG"
  else
    dashboard_cache_status="failed"
    echo "daily_close_finalize|dashboard_cache_clear|failed|url|$DASHBOARD_CACHE_CLEAR_URL" >>"$DETAIL_LOG"
  fi
}

for stage in retry_failed market_monitor deps health; do
  set +e
  run_stage "$stage"
  rc=$?
  set -e
  if [[ "$rc" -ne 0 ]]; then
    failed_stage="$stage"
    failed_rc="$rc"
    print_summary "股票收盘修复失败"
    exit "$rc"
  fi
done
clear_dashboard_cache
print_summary "股票收盘修复完成"
