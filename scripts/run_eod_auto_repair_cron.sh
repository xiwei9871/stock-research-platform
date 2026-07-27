#!/usr/bin/env bash
set -euo pipefail

ROOT="${STOCK_RESEARCH_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${STOCK_RESEARCH_PYTHON:-$ROOT/.venv/bin/python}"
TRADE_DATE="${1:-$(date +%F)}"
LOG_DIR="$ROOT/logs/eod_auto_repair"
OUTPUT_DIR="$ROOT/outputs/research/eod_auto_repair/$TRADE_DATE"
DETAIL_LOG="$LOG_DIR/$TRADE_DATE.log"
LOCK_FILE="$ROOT/.locks/eod_auto_repair.lock"
FLOCK_FILE="$ROOT/.locks/eod_auto_repair.flock"
ACTION_TIMEOUT_SECONDS="${EOD_AUTO_REPAIR_ACTION_TIMEOUT_SECONDS:-43200}"
DASHBOARD_CACHE_CLEAR_URL="${DASHBOARD_CACHE_CLEAR_URL:-http://127.0.0.1:8765/api/dashboard/cache/clear}"
DASHBOARD_AUTH_LOGIN_URL="${DASHBOARD_AUTH_LOGIN_URL:-http://127.0.0.1:8765/api/auth/login}"
DASHBOARD_AUTH_USERNAME="${DASHBOARD_AUTH_USERNAME:-eod_repair}"
DASHBOARD_AUTH_PASSWORD="${DASHBOARD_AUTH_PASSWORD:-}"
DASHBOARD_AUTH_KEYCHAIN_SERVICE="${DASHBOARD_AUTH_KEYCHAIN_SERVICE:-stock-research-dashboard-eod-repair}"
DASHBOARD_WRITE_TOKEN="${DASHBOARD_WRITE_TOKEN:-${STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN:-}}"
CACHE_STATUS="pending"
READINESS_STATUS="pending"
CONTRACT_STATUS="pending"
SYNC_STATUS="pending"
READINESS_JSON="$OUTPUT_DIR/platform_ready.json"
STRATEGY_OUTPUT_DIR="$ROOT/outputs/research/strategy_daily_eod/$TRADE_DATE"
SYNC_SCRIPT="$ROOT/deploy/sync_dashboard_release.sh"

source "$ROOT/scripts/stock_cron_guard.sh"
clear_stock_proxy_env

mkdir -p "$LOG_DIR" "$OUTPUT_DIR" "$(dirname "$LOCK_FILE")"

if [[ -z "$DASHBOARD_AUTH_PASSWORD" ]] && command -v security >/dev/null 2>&1; then
  DASHBOARD_AUTH_PASSWORD="$(
    security find-generic-password \
      -s "$DASHBOARD_AUTH_KEYCHAIN_SERVICE" \
      -a "$DASHBOARD_AUTH_USERNAME" \
      -w 2>/dev/null || true
  )"
fi

acquire_python_lock() {
  while true; do
    if mkdir "$LOCK_FILE" 2>/dev/null; then
      printf '%s\n' "$$" > "$LOCK_FILE/pid"
      trap 'rm -rf "$LOCK_FILE"' EXIT INT TERM
      return 0
    fi

    if [[ -d "$LOCK_FILE" ]]; then
      return 1
    fi

    lock_pid="$(cat "$LOCK_FILE" 2>/dev/null || true)"
    if ! [[ "$lock_pid" =~ ^[0-9]+$ ]]; then
      return 1
    fi
    if kill -0 "$lock_pid" 2>/dev/null; then
      return 1
    fi

    rm -f "$LOCK_FILE" 2>/dev/null || true
  done
}

log_locked() {
  lock_path="$LOCK_FILE"
  if [[ "${LOCK_MODE:-}" == "flock" ]]; then
    lock_path="$FLOCK_FILE"
  fi
  echo "eod_auto_repair|locked|lock_mode|${LOCK_MODE:-unknown}|path|$lock_path" >>"$DETAIL_LOG"
  echo "EOD自动修复跳过"
  echo "交易日: $TRADE_DATE"
  echo "原因: 已有任务运行"
  echo "锁模式: ${LOCK_MODE:-unknown}"
  echo "详细日志: $DETAIL_LOG"
}

clear_dashboard_cache() {
  if [[ -z "${DASHBOARD_CACHE_CLEAR_URL:-}" ]]; then
    CACHE_STATUS="skipped(url_empty)"
    echo "eod_auto_repair|dashboard_cache_clear|skipped|url_empty" >>"$DETAIL_LOG"
    return 1
  fi
  if ! command -v curl >/dev/null 2>&1; then
    CACHE_STATUS="skipped(curl_missing)"
    echo "eod_auto_repair|dashboard_cache_clear|skipped|curl_missing|url|$DASHBOARD_CACHE_CLEAR_URL" >>"$DETAIL_LOG"
    return 1
  fi
  local cookie_jar
  local curl_args
  cookie_jar="$(mktemp "${TMPDIR:-/tmp}/stock-research-dashboard-cache.XXXXXX")"
  curl_args=(-fsS -m 5)
  if [[ -n "${DASHBOARD_AUTH_USERNAME:-}" && -n "${DASHBOARD_AUTH_PASSWORD:-}" ]]; then
    local login_payload
    login_payload="$(printf '{"username":"%s","password":"%s"}' "$DASHBOARD_AUTH_USERNAME" "$DASHBOARD_AUTH_PASSWORD")"
    if curl -fsS -m 5 -c "$cookie_jar" -H "Content-Type: application/json" -X POST "$DASHBOARD_AUTH_LOGIN_URL" --data "$login_payload" >>"$DETAIL_LOG" 2>&1; then
      curl_args+=(-b "$cookie_jar")
      echo "eod_auto_repair|dashboard_cache_clear|auth_login|success|url|$DASHBOARD_AUTH_LOGIN_URL" >>"$DETAIL_LOG"
    else
      echo "eod_auto_repair|dashboard_cache_clear|auth_login|failed|url|$DASHBOARD_AUTH_LOGIN_URL" >>"$DETAIL_LOG"
    fi
  fi
  if [[ -n "${DASHBOARD_WRITE_TOKEN:-}" ]]; then
    curl_args+=(-H "X-Dashboard-Write-Token: $DASHBOARD_WRITE_TOKEN")
  fi
  if curl "${curl_args[@]}" -X POST "$DASHBOARD_CACHE_CLEAR_URL" >>"$DETAIL_LOG" 2>&1; then
    CACHE_STATUS="success"
    echo "eod_auto_repair|dashboard_cache_clear|success|url|$DASHBOARD_CACHE_CLEAR_URL" >>"$DETAIL_LOG"
  else
    CACHE_STATUS="failed"
    echo "eod_auto_repair|dashboard_cache_clear|failed|url|$DASHBOARD_CACHE_CLEAR_URL" >>"$DETAIL_LOG"
    rm -f "$cookie_jar"
    return 1
  fi
  rm -f "$cookie_jar"
  return 0
}

finalize_publication() {
  echo "eod_auto_repair|publication_finalize|platform_readiness|start" >>"$DETAIL_LOG"
  if ! "$PYTHON" -m stock_research.platform_ready \
    --trade-date "$TRADE_DATE" \
    --json-output "$READINESS_JSON" >>"$DETAIL_LOG" 2>&1; then
    READINESS_STATUS="failed"
    CACHE_STATUS="skipped(readiness_failed)"
    SYNC_STATUS="skipped(readiness_failed)"
    return 1
  fi
  if ! jq -e '.status == "ready"' "$READINESS_JSON" >/dev/null 2>&1; then
    READINESS_STATUS="failed"
    CACHE_STATUS="skipped(readiness_not_ready)"
    SYNC_STATUS="skipped(readiness_not_ready)"
    echo "eod_auto_repair|publication_finalize|platform_readiness|failed|status_not_ready" >>"$DETAIL_LOG"
    return 1
  fi
  READINESS_STATUS="success"
  echo "eod_auto_repair|publication_finalize|platform_readiness|success" >>"$DETAIL_LOG"

  "$PYTHON" "$ROOT/deploy/validate_strategy_release.py" \
    --output-dir "$STRATEGY_OUTPUT_DIR" \
    --trade-date "$TRADE_DATE" >>"$DETAIL_LOG" 2>&1 || {
    local rc=$?
    CONTRACT_STATUS="failed"
    CACHE_STATUS="skipped(contract_invalid)"
    SYNC_STATUS="skipped(contract_invalid)"
    return "$rc"
  }
  CONTRACT_STATUS="success"
  echo "eod_auto_repair|publication_finalize|strategy_contract|success" >>"$DETAIL_LOG"

  if ! clear_dashboard_cache; then
    SYNC_STATUS="skipped(cache_failed)"
    return 1
  fi

  if [[ ! -x "$SYNC_SCRIPT" ]]; then
    SYNC_STATUS="failed"
    echo "eod_auto_repair|external_sync|failed|canonical_script_missing" >>"$DETAIL_LOG"
    return 1
  fi
  local sync_rc=0
  if STOCK_RESEARCH_RELEASE_ROOT="$ROOT" \
    STOCK_RESEARCH_PYTHON="$PYTHON" \
    EXPECTED_TRADE_DATE="$TRADE_DATE" \
      "$SYNC_SCRIPT" >>"$DETAIL_LOG" 2>&1; then
    SYNC_STATUS="success"
    echo "eod_auto_repair|external_sync|success" >>"$DETAIL_LOG"
    return 0
  else
    sync_rc=$?
    SYNC_STATUS="failed"
    echo "eod_auto_repair|external_sync|failed|rc=$sync_rc" >>"$DETAIL_LOG"
    return "$sync_rc"
  fi
}

print_summary() {
  local title="$1"
  local rc="$2"
  echo "$title"
  echo "交易日: $TRADE_DATE"
  echo "锁模式: $LOCK_MODE"
  echo "Dashboard缓存: $CACHE_STATUS"
  echo "平台就绪: $READINESS_STATUS"
  echo "策略发布契约: $CONTRACT_STATUS"
  echo "外部同步: $SYNC_STATUS"
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
    --action-timeout-seconds "$ACTION_TIMEOUT_SECONDS" >>"$DETAIL_LOG" 2>&1
  rc=$?
  echo "eod_auto_repair|summary|$OUTPUT_DIR/run_summary.json" >>"$DETAIL_LOG"
  echo "eod_auto_repair|report|$OUTPUT_DIR/run_report.md" >>"$DETAIL_LOG"
  if [[ "$rc" -eq 0 ]]; then
    set +e
    finalize_publication
    rc=$?
    set -e
  else
    CACHE_STATUS="skipped(repair_failed)"
    READINESS_STATUS="skipped(repair_failed)"
    CONTRACT_STATUS="skipped(repair_failed)"
    SYNC_STATUS="skipped(repair_failed)"
    echo "eod_auto_repair|dashboard_cache_clear|skipped|repair_failed" >>"$DETAIL_LOG"
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

if [[ "${EOD_AUTO_REPAIR_DISABLE_FLOCK:-0}" != "1" ]] && command -v flock >/dev/null 2>&1; then
  LOCK_MODE="flock"
  exec 9>"$FLOCK_FILE"
  if ! flock -n 9; then
    log_locked
    exit 0
  fi
  run_repair
  exit "$?"
fi

LOCK_MODE="python_lockfile"
if ! acquire_python_lock; then
  log_locked
  exit 0
fi

run_repair
exit "$?"
