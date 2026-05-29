#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/Users/xiwei/stock_research}"
TRADE_DATE="${TRADE_DATE:-$(date +%F)}"
PORTFOLIO_ID="${PORTFOLIO_ID:-p2_smoke_demo}"
SERVICE="${SERVICE:-stock_research}"
AGGREGATE_REVIEW="${AGGREGATE_REVIEW:-outputs/p2/aggregate/p2_aggregate_review_${TRADE_DATE}.json}"
VIRTUAL_PORTFOLIO="${VIRTUAL_PORTFOLIO:-outputs/p2/simulation/virtual_portfolio_review_${TRADE_DATE}_${PORTFOLIO_ID}.json}"
OUTPUT_DIR="${OUTPUT_DIR:-outputs/p4/operator/${TRADE_DATE}}"
DRY_RUN="${DRY_RUN:-0}"

cd "${PROJECT_DIR}"

run_command() {
  if [[ "${DRY_RUN}" == "1" ]]; then
    printf 'p4_scheduler_wrapper|dry_run'
    printf '|%q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

run_command \
  .venv/bin/stock-research p4-daily-orchestration \
  --trade-date "${TRADE_DATE}" \
  --aggregate-review "${AGGREGATE_REVIEW}" \
  --virtual-portfolio "${VIRTUAL_PORTFOLIO}" \
  --output-dir "${OUTPUT_DIR}" \
  --portfolio-id "${PORTFOLIO_ID}" \
  --apply-daily-run-schema \
  --record-run \
  --service "${SERVICE}"

run_command \
  .venv/bin/stock-research p4-read-model-smoke \
  --trade-date "${TRADE_DATE}" \
  --operator-manifest "${OUTPUT_DIR}/manifest.json" \
  --portfolio-id "${PORTFOLIO_ID}" \
  --service "${SERVICE}"
