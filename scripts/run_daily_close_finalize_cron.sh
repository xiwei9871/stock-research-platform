#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
TRADE_DATE="${TRADE_DATE:-}"

source "$ROOT/scripts/stock_cron_guard.sh"
stock_cron_guard_or_exit "$PYTHON_BIN" "$TRADE_DATE" "${RESEARCH_SERVICE:-}"

resolve_args=()
if [[ -n "${TRADE_DATE}" ]]; then
  resolve_args+=(--date "${TRADE_DATE}")
fi

run_stage() {
  local stage="$1"
  if [[ -n "${TRADE_DATE}" ]]; then
    "${PYTHON_BIN}" -m scripts.daily_pipeline --date "${TRADE_DATE}" --stage "${stage}"
  else
    "${PYTHON_BIN}" -m scripts.daily_pipeline --stage "${stage}"
  fi
}

run_stage retry_failed
run_stage deps
run_stage health
