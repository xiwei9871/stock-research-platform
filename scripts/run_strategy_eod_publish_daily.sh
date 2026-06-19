#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

mkdir -p logs
log_path="${STRATEGY_EOD_PUBLISH_LOG_PATH:-logs/strategy_eod_publish_daily.log}"
trade_date="${1:-${STRATEGY_EOD_TRADE_DATE:-}}"
output_root="${STRATEGY_EOD_OUTPUT_ROOT:-/Users/xiwei/stock_research/outputs}"
python_bin="${PYTHON_BIN:-/Users/xiwei/stock_research/.venv/bin/python}"
args=(--output-root "$output_root")
if [[ -n "$trade_date" ]]; then
  args+=(--trade-date "$trade_date")
fi

timestamp() {
  date '+%Y-%m-%dT%H:%M:%S%z'
}

{
  printf '%s strategy eod publish starting\n' "$(timestamp)"
  printf 'repo_root=%s\n' "$repo_root"
  printf 'trade_date=%s\n' "${trade_date:-latest-market-date}"
  printf 'output_root=%s\n' "$output_root"
  PYTHONPATH=src "$python_bin" -m stock_research.strategy_eod_publish "${args[@]}"
  printf '%s strategy eod publish complete\n' "$(timestamp)"
} >> "$log_path" 2>&1
