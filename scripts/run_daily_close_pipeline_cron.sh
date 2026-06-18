#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
TRADE_DATE="${TRADE_DATE:-}"
STAGE="${1:-all}"

if [[ -n "${TRADE_DATE}" ]]; then
  "${PYTHON_BIN}" -m scripts.daily_pipeline --date "${TRADE_DATE}" --stage "${STAGE}"
else
  "${PYTHON_BIN}" -m scripts.daily_pipeline --stage "${STAGE}"
fi
