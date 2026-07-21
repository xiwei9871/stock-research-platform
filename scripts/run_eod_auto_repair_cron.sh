#!/usr/bin/env bash
set -euo pipefail

ROOT="${STOCK_RESEARCH_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${STOCK_RESEARCH_PYTHON:-$ROOT/.venv/bin/python}"
JSON_PYTHON="${STOCK_RESEARCH_JSON_PYTHON:-python3}"
TRADE_DATE="${1:-$(date +%F)}"
LOG_DIR="$ROOT/logs/eod_auto_repair"
OUTPUT_DIR="$ROOT/outputs/research/eod_auto_repair/$TRADE_DATE"
DETAIL_LOG="$LOG_DIR/$TRADE_DATE.log"
LOCK_FILE="$ROOT/.locks/eod_auto_repair.lock"
FLOCK_FILE="$ROOT/.locks/eod_auto_repair.flock"
ACTION_TIMEOUT_SECONDS="${EOD_AUTO_REPAIR_ACTION_TIMEOUT_SECONDS:-43200}"
DASHBOARD_CACHE_CLEAR_URL="${DASHBOARD_CACHE_CLEAR_URL:-http://127.0.0.1:8765/api/dashboard/cache/clear}"
DASHBOARD_AUTH_LOGIN_URL="${DASHBOARD_AUTH_LOGIN_URL:-http://127.0.0.1:8765/api/auth/login}"
DASHBOARD_AUTH_USERNAME="${DASHBOARD_AUTH_USERNAME:-}"
DASHBOARD_AUTH_PASSWORD="${DASHBOARD_AUTH_PASSWORD:-}"
DASHBOARD_WRITE_TOKEN="${DASHBOARD_WRITE_TOKEN:-${STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN:-}}"
CACHE_STATUS="pending"
BROWSER_STATUS="unknown"
BROWSER_EVIDENCE_PATHS=""

source "$ROOT/scripts/stock_cron_guard.sh"
clear_stock_proxy_env

mkdir -p "$LOG_DIR" "$OUTPUT_DIR" "$(dirname "$LOCK_FILE")"

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
    return 0
  fi
  if ! command -v curl >/dev/null 2>&1; then
    CACHE_STATUS="skipped(curl_missing)"
    echo "eod_auto_repair|dashboard_cache_clear|skipped|curl_missing|url|$DASHBOARD_CACHE_CLEAR_URL" >>"$DETAIL_LOG"
    return 0
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
  fi
  rm -f "$cookie_jar"
}

parse_browser_summary() {
  "$JSON_PYTHON" - "$1" <<'PY'
import json
import sys

STATUS_LABELS = {
    "success": "通过",
    "degraded": "降级",
    "failed": "失败",
    "blocked": "阻塞",
    "skipped": "跳过",
}

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
browser = payload.get("browser_acceptance")
if not isinstance(browser, dict):
    raise SystemExit(1)
check = browser.get("check")
if isinstance(check, dict):
    status = check.get("status")
else:
    action = browser.get("action")
    status = action.get("status") if isinstance(action, dict) else None
if status not in STATUS_LABELS:
    raise SystemExit(1)
print(f"STATUS\t{STATUS_LABELS[status]}")

paths = []
action = browser.get("action")
if isinstance(action, dict) and isinstance(action.get("artifact_paths"), list):
    paths.extend(action["artifact_paths"])
if isinstance(check, dict):
    metrics = check.get("metrics")
    if isinstance(metrics, dict) and isinstance(metrics.get("artifact_paths"), list):
        paths.extend(metrics["artifact_paths"])
seen = set()
for path in paths:
    if not isinstance(path, str) or not path or path in seen:
        continue
    if any(ord(character) < 32 or ord(character) == 127 for character in path):
        continue
    seen.add(path)
    print(f"EVIDENCE\t{path}")
PY
}

print_summary() {
  local title="$1"
  local rc="$2"
  echo "$title"
  echo "交易日: $TRADE_DATE"
  echo "锁模式: $LOCK_MODE"
  echo "Dashboard缓存: $CACHE_STATUS"
  echo "摘要文件: $OUTPUT_DIR/run_summary.json"
  echo "报告文件: $OUTPUT_DIR/run_report.md"
  echo "HTML报告: $OUTPUT_DIR/run_report.html"
  echo "浏览器验收状态: $BROWSER_STATUS"
  if [[ -n "$BROWSER_EVIDENCE_PATHS" ]]; then
    while IFS= read -r evidence_path; do
      [[ -n "$evidence_path" ]] && echo "浏览器证据: $evidence_path"
    done <<< "$BROWSER_EVIDENCE_PATHS"
  else
    echo "浏览器证据: none"
  fi
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
  PLAYWRIGHT_EOD_OUTPUT_DIR="$OUTPUT_DIR/browser" rtk "$PYTHON" -m stock_research.eod_auto_repair \
    --trade-date "$TRADE_DATE" \
    --output-dir "$OUTPUT_DIR" \
    --mode loop \
    --action-timeout-seconds "$ACTION_TIMEOUT_SECONDS" >>"$DETAIL_LOG" 2>&1
  rc=$?
  echo "eod_auto_repair|summary|$OUTPUT_DIR/run_summary.json" >>"$DETAIL_LOG"
  echo "eod_auto_repair|report|$OUTPUT_DIR/run_report.md" >>"$DETAIL_LOG"
  echo "eod_auto_repair|html_report|$OUTPUT_DIR/run_report.html" >>"$DETAIL_LOG"
  if [[ -f "$OUTPUT_DIR/run_summary.json" ]]; then
    parsed_browser_records="$(parse_browser_summary "$OUTPUT_DIR/run_summary.json" 2>>"$DETAIL_LOG")"
    if [[ -n "$parsed_browser_records" ]]; then
      while IFS=$'\t' read -r record_type record_value; do
        if [[ "$record_type" == "STATUS" ]]; then
          BROWSER_STATUS="$record_value"
        elif [[ "$record_type" == "EVIDENCE" ]]; then
          if [[ -n "$BROWSER_EVIDENCE_PATHS" ]]; then
            BROWSER_EVIDENCE_PATHS+=$'\n'
          fi
          BROWSER_EVIDENCE_PATHS+="$record_value"
        fi
      done <<< "$parsed_browser_records"
    fi
  fi
  echo "eod_auto_repair|browser_status|$BROWSER_STATUS" >>"$DETAIL_LOG"
  if [[ -n "$BROWSER_EVIDENCE_PATHS" ]]; then
    while IFS= read -r evidence_path; do
      [[ -n "$evidence_path" ]] && echo "eod_auto_repair|browser_evidence|$evidence_path" >>"$DETAIL_LOG"
    done <<< "$BROWSER_EVIDENCE_PATHS"
  fi
  clear_dashboard_cache
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
