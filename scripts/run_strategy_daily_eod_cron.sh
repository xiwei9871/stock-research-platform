#!/usr/bin/env bash
set -euo pipefail

ROOT="${STRATEGY_DAILY_EOD_ROOT:-/Users/xiwei/stock_research}"
cd "$ROOT"

PYTHON_BIN="${STRATEGY_DAILY_EOD_PYTHON:-$ROOT/.venv/bin/python}"
TRADE_DATE="${STRATEGY_DAILY_EOD_TRADE_DATE:-${TRADE_DATE:-}}"
OUTPUT_ROOT="${STRATEGY_DAILY_EOD_OUTPUT_ROOT:-$ROOT/outputs/research/strategy_daily_eod}"

source "$ROOT/scripts/stock_cron_guard.sh"
clear_stock_proxy_env
stock_cron_guard_or_exit "$PYTHON_BIN" "$TRADE_DATE" "${RESEARCH_SERVICE:-}"

if [[ -z "${TRADE_DATE}" ]]; then
  TRADE_DATE="$("$PYTHON_BIN" -c 'from datetime import date; print(date.today().isoformat())')"
fi

set +e
output="$(PYTHONPATH=src "$PYTHON_BIN" -m stock_research.cli run-strategy-daily-eod \
  --trade-date "$TRADE_DATE" \
  --output-root "$OUTPUT_ROOT" 2>&1)"
rc=$?
set -e

printf '%s\n' "$output"
if [[ "$rc" -ne 0 ]]; then
  exit "$rc"
fi

if printf '%s\n' "$output" | grep -q '^strategy_daily_eod|status|failed$'; then
  echo "strategy_daily_eod|business_failed|trade_date|${TRADE_DATE}" >&2
  exit 1
fi
