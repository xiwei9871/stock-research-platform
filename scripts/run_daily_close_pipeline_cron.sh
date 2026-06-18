#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
TRADE_DATE="${TRADE_DATE:-}"
STAGE="${1:-all}"

date_arg=()
if [[ -n "${TRADE_DATE}" ]]; then
  date_arg=(--date "${TRADE_DATE}")
fi

"${PYTHON_BIN}" -m scripts.daily_pipeline "${date_arg[@]}" --stage "${STAGE}"
