#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
TRADE_DATE="${TRADE_DATE:-}"

resolve_args=()
if [[ -n "${TRADE_DATE}" ]]; then
  resolve_args+=(--date "${TRADE_DATE}")
fi

run_stage() {
  local stage="$1"
  "${PYTHON_BIN}" -m scripts.daily_pipeline "${resolve_args[@]}" --stage "${stage}"
}

run_stage retry_failed
run_stage deps
run_stage health
