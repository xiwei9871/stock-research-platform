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
P5_NOTIFY="${P5_NOTIFY:-0}"
P5_NOTIFY_FEISHU_PREVIEW="${P5_NOTIFY_FEISHU_PREVIEW:-0}"
P5_OUTPUT_DIR="${P5_OUTPUT_DIR:-outputs/p5/notifications/${TRADE_DATE}}"
P5_SMOKE_LOG="${P5_SMOKE_LOG:-${P5_OUTPUT_DIR}/p4_read_model_smoke.log}"

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

SMOKE_COMMAND=(
  .venv/bin/stock-research p4-read-model-smoke
  --trade-date "${TRADE_DATE}"
  --operator-manifest "${OUTPUT_DIR}/manifest.json"
  --portfolio-id "${PORTFOLIO_ID}"
  --service "${SERVICE}"
)

if [[ "${DRY_RUN}" == "1" ]]; then
  run_command "${SMOKE_COMMAND[@]}"
else
  mkdir -p "$(dirname "${P5_SMOKE_LOG}")"
  "${SMOKE_COMMAND[@]}" | tee "${P5_SMOKE_LOG}"
fi

if [[ "${P5_NOTIFY}" == "1" ]]; then
  P5_NOTIFY_COMMAND=(
    .venv/bin/python scripts/run_p5_notify_p4_smoke.py
    --smoke-log "${P5_SMOKE_LOG}"
    --output-dir "${P5_OUTPUT_DIR}"
    --source-command "stock-research p4-read-model-smoke --trade-date ${TRADE_DATE}"
  )
  if [[ "${P5_NOTIFY_FEISHU_PREVIEW}" == "1" ]]; then
    P5_NOTIFY_COMMAND+=(--feishu-preview)
  fi
  run_command "${P5_NOTIFY_COMMAND[@]}"
else
  printf 'p4_scheduler_wrapper|p5_notify|disabled\n'
fi
