#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
TRADE_DATE="${TRADE_DATE:-}"
STAGE="${1:-all}"
SMOKE_ONLY="${DAILY_CLOSE_SMOKE_ONLY:-0}"

source "$ROOT/scripts/stock_cron_guard.sh"
clear_stock_proxy_env
stock_cron_guard_or_exit "$PYTHON_BIN" "$TRADE_DATE" "${RESEARCH_SERVICE:-}"

if [[ "$SMOKE_ONLY" == "1" ]]; then
  echo "daily_close_pipeline|smoke|would_run|stage=${STAGE}|trade_date=${TRADE_DATE:-auto}"
  exit 0
fi

output_file="$(mktemp "${TMPDIR:-/tmp}/daily_close_pipeline.XXXXXX")"
cleanup() {
  rm -f "$output_file" 2>/dev/null || true
}
trap cleanup EXIT

set +e
if [[ -n "${TRADE_DATE}" ]]; then
  "${PYTHON_BIN}" -m scripts.daily_pipeline --date "${TRADE_DATE}" --stage "${STAGE}" 2>&1 | tee "$output_file"
  rc=${PIPESTATUS[0]}
else
  "${PYTHON_BIN}" -m scripts.daily_pipeline --stage "${STAGE}" 2>&1 | tee "$output_file"
  rc=${PIPESTATUS[0]}
fi
set -e

if [[ "$rc" -ne 0 ]]; then
  exit "$rc"
fi

if [[ "$STAGE" == "minute5" ]] && grep -Eq '"status"[[:space:]]*:[[:space:]]*"failed"' "$output_file"; then
  echo "daily_close_pipeline|business_failed|stage=minute5|trade_date=${TRADE_DATE:-auto}" >&2
  exit 1
fi
