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

READINESS_JSON="${PLATFORM_READY_READINESS_JSON:-$REPAIR_OUTPUT_DIR/platform_ready.json}"
STRATEGY_OUTPUT_DIR="${PLATFORM_READY_STRATEGY_OUTPUT_DIR:-$OUTPUT_DIR/strategy_daily_eod/$TRADE_DATE}"
SYNC_SCRIPT="${PLATFORM_READY_SYNC_SCRIPT:-$ROOT/deploy/sync_dashboard_release.sh}"
CACHE_CLEAR_URL="${DASHBOARD_CACHE_CLEAR_URL:-http://127.0.0.1:8765/api/dashboard/cache/clear}"
CURL_BIN="${PLATFORM_READY_CURL:-curl}"
DASHBOARD_AUTH_LOGIN_URL="${DASHBOARD_AUTH_LOGIN_URL:-http://127.0.0.1:8765/api/auth/login}"
DASHBOARD_AUTH_USERNAME="${DASHBOARD_AUTH_USERNAME:-eod_repair}"
DASHBOARD_AUTH_PASSWORD="${DASHBOARD_AUTH_PASSWORD:-}"
DASHBOARD_AUTH_KEYCHAIN_SERVICE="${DASHBOARD_AUTH_KEYCHAIN_SERVICE:-stock-research-dashboard-eod-repair}"
DASHBOARD_WRITE_TOKEN="${DASHBOARD_WRITE_TOKEN:-${STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN:-}}"

mkdir -p "$LOG_DIR" "$OUTPUT_DIR" "$REPAIR_OUTPUT_DIR" "$(dirname "$RUN_LOG")"

source "$ROOT/scripts/stock_cron_guard.sh"
clear_stock_proxy_env

if [[ -z "$DASHBOARD_AUTH_PASSWORD" ]] && command -v security >/dev/null 2>&1; then
  DASHBOARD_AUTH_PASSWORD="$(
    security find-generic-password \
      -s "$DASHBOARD_AUTH_KEYCHAIN_SERVICE" \
      -a "$DASHBOARD_AUTH_USERNAME" \
      -w 2>/dev/null || true
  )"
fi

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

clear_dashboard_cache() {
  local cookie_jar
  local curl_args
  cookie_jar="$(mktemp "${TMPDIR:-/tmp}/stock-research-platform-ready-cache.XXXXXX")"
  curl_args=(-fsS -m 5)
  if [[ -n "$DASHBOARD_AUTH_USERNAME" && -n "$DASHBOARD_AUTH_PASSWORD" ]]; then
    local login_payload
    login_payload="$(printf '{"username":"%s","password":"%s"}' "$DASHBOARD_AUTH_USERNAME" "$DASHBOARD_AUTH_PASSWORD")"
    if "$CURL_BIN" -fsS -m 5 -c "$cookie_jar" -H "Content-Type: application/json" \
      -X POST "$DASHBOARD_AUTH_LOGIN_URL" --data "$login_payload" >>"$RUN_LOG" 2>&1; then
      curl_args+=(-b "$cookie_jar")
    fi
  fi
  if [[ -n "$DASHBOARD_WRITE_TOKEN" ]]; then
    curl_args+=(-H "X-Dashboard-Write-Token: $DASHBOARD_WRITE_TOKEN")
  fi
  if "$CURL_BIN" "${curl_args[@]}" -X POST "$CACHE_CLEAR_URL" >>"$RUN_LOG" 2>&1; then
    rm -f "$cookie_jar"
    return 0
  fi
  rm -f "$cookie_jar"
  return 1
}

finalize_publication() {
  "$PYTHON" -m stock_research.platform_ready \
    --trade-date "$TRADE_DATE" \
    --reports-dir "$REPORTS_DIR" \
    --json-output "$READINESS_JSON" >>"$RUN_LOG" 2>&1 || return $?
  jq -e '.status == "ready"' "$READINESS_JSON" >/dev/null 2>&1 || return 1
  "$PYTHON" "$ROOT/deploy/validate_strategy_release.py" \
    --output-dir "$STRATEGY_OUTPUT_DIR" \
    --trade-date "$TRADE_DATE" >>"$RUN_LOG" 2>&1 || return $?
  clear_dashboard_cache || return $?
  [[ -x "$SYNC_SCRIPT" ]] || return 1
  STOCK_RESEARCH_RELEASE_ROOT="$ROOT" \
  STOCK_RESEARCH_PYTHON="$PYTHON" \
  EXPECTED_TRADE_DATE="$TRADE_DATE" \
    "$SYNC_SCRIPT" >>"$RUN_LOG" 2>&1
}

forward_signal() {
  if [[ -n "$PIPELINE_PID" ]]; then
    kill -TERM "$PIPELINE_PID" 2>/dev/null || true
  fi
}

trap forward_signal TERM INT
trap cleanup_heartbeat EXIT

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
if [ "$rc" -ne 0 ]; then
  print_summary "EOD自动修复失败" "$rc"
else
  set +e
  finalize_publication
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    print_summary "EOD自动修复发布失败" "$rc"
  else
    print_summary "EOD自动修复完成" "$rc"
  fi
fi
exit "$rc"
