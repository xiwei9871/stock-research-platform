#!/usr/bin/env bash
set -euo pipefail

ROOT="${TDX_AUCTION_WATCHDOG_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${TDX_AUCTION_WATCHDOG_PYTHON:-$ROOT/.venv/bin/python}"
OPENCLAW_BIN="${TDX_AUCTION_WATCHDOG_OPENCLAW_BIN:-$ROOT/scripts/openclaw_runtime_cli.sh}"
LOG_DIR="${TDX_AUCTION_WATCHDOG_LOG_DIR:-$ROOT/logs}"
RUN_LOG="${TDX_AUCTION_WATCHDOG_RUN_LOG:-$LOG_DIR/tdx_auction_backfill_watchdog.host.log}"
LOCK_PATH="${TDX_AUCTION_WATCHDOG_LOCK_DIR:-$LOG_DIR/tdx_auction_backfill_watchdog.lock}"
START_DATE="${TDX_AUCTION_WATCHDOG_START_DATE:-2018-02-14}"
END_DATE="${TDX_AUCTION_WATCHDOG_END_DATE:-2024-12-31}"
MAX_JOBS="${TDX_AUCTION_WATCHDOG_MAX_JOBS:-4}"
WORKERS="${TDX_AUCTION_WATCHDOG_WORKERS:-8}"
STALE_AFTER_MINUTES="${TDX_AUCTION_WATCHDOG_STALE_AFTER_MINUTES:-60}"
RUN_TIMEOUT_SECONDS="${TDX_AUCTION_WATCHDOG_RUN_TIMEOUT_SECONDS:-3600}"
TDX_HOSTS="${TDX_AUCTION_WATCHDOG_HOSTS:-116.205.183.150:7709,116.205.171.132:7709,111.230.186.52:7709,129.204.230.128:7709}"
TDX_TIMEOUT_SECONDS="${TDX_AUCTION_WATCHDOG_TIMEOUT_SECONDS:-8}"
TDX_SERVER_COUNT="${TDX_AUCTION_WATCHDOG_SERVER_COUNT:-4}"
TDX_CONNECTIONS_PER_SERVER="${TDX_AUCTION_WATCHDOG_CONNECTIONS_PER_SERVER:-1}"
RETRY_ATTEMPTS="${TDX_AUCTION_WATCHDOG_RETRY_ATTEMPTS:-2}"
RETRY_SLEEP_SECONDS="${TDX_AUCTION_WATCHDOG_RETRY_SLEEP_SECONDS:-0.25}"
MAX_PAGES="${TDX_AUCTION_WATCHDOG_MAX_PAGES:-100}"
REPORT_TARGET="${TDX_AUCTION_WATCHDOG_REPORT_TARGET:-chat:oc_82dd978138a0cde5864868c5b5b8e754}"
REPORT_ACCOUNT="${TDX_AUCTION_WATCHDOG_REPORT_ACCOUNT:-jarvis}"
LEDGER_PATH="${TDX_AUCTION_WATCHDOG_LEDGER_PATH:-$ROOT/outputs/research/tdx_auction_backfill_watchdog/reported_months.json}"
COMPLETION_SENTINEL="${TDX_AUCTION_WATCHDOG_COMPLETION_SENTINEL:-$LOG_DIR/tdx_auction_backfill_watchdog.completed}"
COMPLETION_KEY="${TDX_AUCTION_WATCHDOG_COMPLETION_KEY:-tdx-auction|$START_DATE|$END_DATE|max$MAX_JOBS|workers$WORKERS|timeout$RUN_TIMEOUT_SECONDS}"
RUN_OUTPUT=""

mkdir -p "$LOG_DIR"
mkdir -p "$(dirname "$RUN_LOG")"
exec >> "$RUN_LOG" 2>&1

echo "=== TDX auction backfill watchdog host run start: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
echo "cwd=$ROOT"
echo "python=$PYTHON"
echo "openclaw_bin=$OPENCLAW_BIN"
echo "start_date=$START_DATE"
echo "end_date=$END_DATE"
echo "max_jobs=$MAX_JOBS"
echo "workers=$WORKERS"
echo "tdx_hosts=$TDX_HOSTS"
echo "tdx_server_count=$TDX_SERVER_COUNT"
echo "completion_sentinel=$COMPLETION_SENTINEL"

if [ -f "$COMPLETION_SENTINEL" ] && [ "$(cat "$COMPLETION_SENTINEL")" = "$COMPLETION_KEY" ]; then
  echo "skipped because backfill completion sentinel is current"
  echo "=== TDX auction backfill watchdog host run end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=0 ==="
  exit 0
fi

if mkdir "$LOCK_PATH" 2>/dev/null; then
  LOCK_ACQUIRED=true
else
  LOCK_ACQUIRED=false
fi
echo "lock_acquired=$LOCK_ACQUIRED"
if [ "$LOCK_ACQUIRED" != "true" ]; then
  echo "skipped because another TDX auction watchdog is running"
  exit 0
fi

cleanup() {
  rmdir "$LOCK_PATH" 2>/dev/null || true
  if [ -n "$RUN_OUTPUT" ]; then
    rm -f "$RUN_OUTPUT" 2>/dev/null || true
  fi
}
trap cleanup EXIT

cd "$ROOT"
RUN_OUTPUT="$(mktemp "$LOG_DIR/tdx_auction_backfill_watchdog.XXXXXX")"

run_watchdog_command() {
  "$PYTHON" -m stock_research.cli tdx-auction-backfill-watchdog \
    --start-date "$START_DATE" \
    --end-date "$END_DATE" \
    --max-jobs "$MAX_JOBS" \
    --workers "$WORKERS" \
    --stale-after-minutes "$STALE_AFTER_MINUTES" \
    --run-timeout-seconds "$RUN_TIMEOUT_SECONDS" \
    --tdx-hosts "$TDX_HOSTS" \
    --tdx-timeout-seconds "$TDX_TIMEOUT_SECONDS" \
    --tdx-server-count "$TDX_SERVER_COUNT" \
    --tdx-connections-per-server "$TDX_CONNECTIONS_PER_SERVER" \
    --retry-attempts "$RETRY_ATTEMPTS" \
    --retry-sleep-seconds "$RETRY_SLEEP_SECONDS" \
    --max-pages "$MAX_PAGES" \
    --report-target "$REPORT_TARGET" \
    --report-account "$REPORT_ACCOUNT" \
    --openclaw-bin "$OPENCLAW_BIN" \
    --ledger-path "$LEDGER_PATH" \
    "$@"
}

set +e
if [ "${TDX_AUCTION_WATCHDOG_REPORT_DRY_RUN:-0}" = "1" ]; then
  run_watchdog_command --report-dry-run 2>&1 | tee "$RUN_OUTPUT"
else
  run_watchdog_command 2>&1 | tee "$RUN_OUTPUT"
fi
rc=${PIPESTATUS[0]}
set -e

if [ "$rc" -eq 0 ] \
  && grep -Eq '\|action\|healthy$' "$RUN_OUTPUT" \
  && grep -Eq '\|work_remaining\|False$' "$RUN_OUTPUT" \
  && ! grep -Eq '\|month_report\|.*\|sent\|False$' "$RUN_OUTPUT"; then
  printf '%s\n' "$COMPLETION_KEY" > "$COMPLETION_SENTINEL"
  echo "completion_sentinel_written=true"
else
  echo "completion_sentinel_written=false"
fi

echo "=== TDX auction backfill watchdog host run end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ==="
exit "$rc"
