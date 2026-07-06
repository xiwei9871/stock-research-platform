#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
TRADE_DATE="${TRADE_DATE:-}"
DASHBOARD_CACHE_CLEAR_URL="${DASHBOARD_CACHE_CLEAR_URL:-http://127.0.0.1:8765/api/dashboard/cache/clear}"
SMOKE_ONLY="${DAILY_CLOSE_SMOKE_ONLY:-0}"

source "$ROOT/scripts/stock_cron_guard.sh"
clear_stock_proxy_env
stock_cron_guard_or_exit "$PYTHON_BIN" "$TRADE_DATE" "${RESEARCH_SERVICE:-}"

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

run_stage_command() {
  local stage="$1"
  shift
  local timeout_seconds="${FINALIZE_STAGE_TIMEOUT_SECONDS:-2700}"

  if [[ ! "$timeout_seconds" =~ ^[0-9]+$ ]] || [[ "$timeout_seconds" -le 0 ]]; then
    "$@"
    return $?
  fi

  "$@" &
  local child_pid=$!
  local elapsed=0
  local heartbeat_seconds="${FINALIZE_STAGE_HEARTBEAT_SECONDS:-60}"
  if [[ ! "$heartbeat_seconds" =~ ^[0-9]+$ ]] || [[ "$heartbeat_seconds" -le 0 ]]; then
    heartbeat_seconds=0
  fi
  while kill -0 "$child_pid" 2>/dev/null; do
    if [[ "$elapsed" -ge "$timeout_seconds" ]]; then
      echo "daily_close_finalize|stage|${stage}|timeout|${timeout_seconds}" >&2
      kill -TERM "$child_pid" 2>/dev/null || true
      sleep 2
      kill -KILL "$child_pid" 2>/dev/null || true
      wait "$child_pid" 2>/dev/null || true
      return 124
    fi
    sleep 1
    elapsed=$((elapsed + 1))
    if [[ "$heartbeat_seconds" -gt 0 && $((elapsed % heartbeat_seconds)) -eq 0 ]]; then
      echo "daily_close_finalize|stage|${stage}|heartbeat|elapsed=${elapsed}"
    fi
  done
  wait "$child_pid"
}

run_stage() {
  local stage="$1"
  echo "daily_close_finalize|stage|${stage}|start|$(date '+%Y-%m-%d %H:%M:%S %z')"
  local rc=0
  set +e
  if [[ -n "${TRADE_DATE}" ]]; then
    run_stage_command "${stage}" "${PYTHON_BIN}" -m scripts.daily_pipeline --date "${TRADE_DATE}" --stage "${stage}"
    rc=$?
  else
    run_stage_command "${stage}" "${PYTHON_BIN}" -m scripts.daily_pipeline --stage "${stage}"
    rc=$?
  fi
  set -e
  if [[ "$rc" -ne 0 ]]; then
    echo "daily_close_finalize|stage|${stage}|failed|rc=${rc}|$(date '+%Y-%m-%d %H:%M:%S %z')" >&2
    return "$rc"
  fi
  echo "daily_close_finalize|stage|${stage}|done|$(date '+%Y-%m-%d %H:%M:%S %z')"
}

clear_dashboard_cache() {
  if [[ -z "${DASHBOARD_CACHE_CLEAR_URL:-}" ]]; then
    echo "daily_close_finalize|dashboard_cache_clear|skipped|url_empty"
    return 0
  fi
  if ! command -v curl >/dev/null 2>&1; then
    echo "daily_close_finalize|dashboard_cache_clear|skipped|curl_missing|url|$DASHBOARD_CACHE_CLEAR_URL"
    return 0
  fi
  if curl -fsS -m 5 -X POST "$DASHBOARD_CACHE_CLEAR_URL" >/dev/null; then
    echo "daily_close_finalize|dashboard_cache_clear|success|url|$DASHBOARD_CACHE_CLEAR_URL"
  else
    echo "daily_close_finalize|dashboard_cache_clear|failed|url|$DASHBOARD_CACHE_CLEAR_URL"
  fi
}

run_stage retry_failed
run_stage market_monitor
run_stage deps
run_stage health
clear_dashboard_cache
