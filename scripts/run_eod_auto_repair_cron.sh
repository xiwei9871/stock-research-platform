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
DASHBOARD_AUTH_USERNAME="${DASHBOARD_AUTH_USERNAME:-eod_repair}"
DASHBOARD_AUTH_PASSWORD="${DASHBOARD_AUTH_PASSWORD:-}"
DASHBOARD_AUTH_KEYCHAIN_SERVICE="${DASHBOARD_AUTH_KEYCHAIN_SERVICE:-stock-research-dashboard-eod-repair}"

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
export DASHBOARD_AUTH_PASSWORD

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

finalize_publication() {
  local repair_rc="$1"
  rtk "$PYTHON" -m stock_research.eod_auto_repair \
    --finalize-publication \
    --trade-date "$TRADE_DATE" \
    --output-dir "$OUTPUT_DIR" \
    --release-root "$ROOT" \
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
    --action-timeout-seconds "$ACTION_TIMEOUT_SECONDS" >>"$DETAIL_LOG" 2>&1
  rc=$?
  echo "eod_auto_repair|summary|$OUTPUT_DIR/run_summary.json" >>"$DETAIL_LOG"
  echo "eod_auto_repair|report|$OUTPUT_DIR/run_report.md" >>"$DETAIL_LOG"
  repair_rc=$rc
  finalize_publication "$repair_rc"
  rc=$?
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
