#!/usr/bin/env bash
set -euo pipefail

ROOT="${TRADING_CALENDAR_SYNC_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${TRADING_CALENDAR_SYNC_PYTHON:-$ROOT/.venv/bin/python}"
LOG_DIR="${TRADING_CALENDAR_SYNC_LOG_DIR:-$ROOT/logs}"
RUN_LOG="${TRADING_CALENDAR_SYNC_RUN_LOG:-$LOG_DIR/trading_calendar_sync.host.log}"
DAYS_AHEAD="${TRADING_CALENDAR_SYNC_DAYS_AHEAD:-120}"
EXCHANGES="${TRADING_CALENDAR_SYNC_EXCHANGES:-SH,SZ}"
SOURCE_VERSION="${TRADING_CALENDAR_SYNC_SOURCE_VERSION:-tushare_trade_cal_v1}"
MAX_RETRIES="${TRADING_CALENDAR_SYNC_MAX_RETRIES:-2}"
RETRY_SLEEP_SECONDS="${TRADING_CALENDAR_SYNC_RETRY_SLEEP_SECONDS:-3700}"
SERVICE="${RESEARCH_SERVICE:-}"

source "$ROOT/scripts/stock_cron_guard.sh"
clear_stock_proxy_env

START_DATE="${TRADING_CALENDAR_SYNC_START_DATE:-$("$PYTHON" - <<'PY'
from datetime import date
print(date.today().isoformat())
PY
)}"
END_DATE="${TRADING_CALENDAR_SYNC_END_DATE:-$("$PYTHON" - <<PY
from datetime import date, timedelta
print((date.fromisoformat("$START_DATE") + timedelta(days=int("$DAYS_AHEAD"))).isoformat())
PY
)}"

mkdir -p "$LOG_DIR" "$(dirname "$RUN_LOG")"

args=(
  -m stock_research.cli sync-tushare-trading-calendar
  --start-date "$START_DATE"
  --end-date "$END_DATE"
  --exchanges "$EXCHANGES"
  --source-version "$SOURCE_VERSION"
  --max-retries "$MAX_RETRIES"
  --retry-sleep-seconds "$RETRY_SLEEP_SECONDS"
)
if [[ -n "$SERVICE" ]]; then
  args+=(--service "$SERVICE")
fi

print_summary() {
  local title="$1"
  local rc="$2"
  echo "$title"
  echo "范围: $START_DATE ~ $END_DATE"
  echo "交易所: $EXCHANGES"
  if [[ "$rc" -ne 0 ]]; then
    echo "退出码: $rc"
  fi
  echo "详细日志: $RUN_LOG"
}

echo "=== trading calendar sync start: $(date '+%Y-%m-%d %H:%M:%S %z') ===" >>"$RUN_LOG"
echo "start_date=$START_DATE" >>"$RUN_LOG"
echo "end_date=$END_DATE" >>"$RUN_LOG"
echo "exchanges=$EXCHANGES" >>"$RUN_LOG"
cd "$ROOT"
set +e
"$PYTHON" "${args[@]}" >>"$RUN_LOG" 2>&1
rc=$?
set -e
echo "=== trading calendar sync end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ===" >>"$RUN_LOG"
if [[ "$rc" -ne 0 ]]; then
  print_summary "交易日历同步失败" "$rc"
else
  print_summary "交易日历同步完成" "$rc"
fi
exit "$rc"
