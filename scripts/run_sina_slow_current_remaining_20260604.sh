#!/usr/bin/env bash
set -uo pipefail

BASE="outputs/research/stock_report_web_gap_20260603"
CHUNKS="$BASE/sina_slow_current_remaining_20260604_plan_chunks"
OUTROOT="$BASE/sina_slow_current_remaining_20260604"

mkdir -p "$OUTROOT"

for f in "$CHUNKS"/chunk_*.csv; do
  name="$(basename "$f" .csv)"
  out="$OUTROOT/$name"
  mkdir -p "$out"

  echo "batch_start|$(date +%Y-%m-%dT%H:%M:%S%z)|$name|plan=$f|out=$out"
  .venv/bin/stock-research collect-stock-report-web-sources \
    --search-plan-path "$f" \
    --output-dir "$out" \
    --adapter sina_report_page \
    --max-results-per-task 20 \
    --workers 1 \
    --progress-every 5 \
    --request-sleep-seconds 10 \
    --stop-after-consecutive-fetch-errors 50 \
    --start-date 2025-01-01 \
    --end-date 2026-06-04 \
    --write-db
  rc=$?
  echo "batch_done|$(date +%Y-%m-%dT%H:%M:%S%z)|$name|rc=$rc"

  sleep 30
done

echo "all_done|$(date +%Y-%m-%dT%H:%M:%S%z)"
