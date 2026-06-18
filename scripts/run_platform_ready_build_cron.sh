#!/usr/bin/env bash
set -euo pipefail

ROOT="${PLATFORM_READY_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${PLATFORM_READY_PYTHON:-$ROOT/.venv/bin/python}"
LOG_DIR="${PLATFORM_READY_LOG_DIR:-$ROOT/logs}"
RUN_LOG="${PLATFORM_READY_RUN_LOG:-$LOG_DIR/platform_ready_build.host.log}"
TRADE_DATE="${PLATFORM_READY_TRADE_DATE:-}"
OUTPUT_DIR="${PLATFORM_READY_OUTPUT_DIR:-$ROOT/outputs/research}"
REPORTS_DIR="${PLATFORM_READY_REPORTS_DIR:-$ROOT/reports}"
OPENCLAW_BIN="${PLATFORM_READY_OPENCLAW_BIN:-$ROOT/scripts/openclaw_runtime_cli.sh}"
ENRICH_DATASETS="${PLATFORM_READY_ENRICH_DATASETS:-lhb,repurchase,survey,forecast,express}"

if [ -z "$TRADE_DATE" ]; then
  TRADE_DATE="$("$PYTHON" - <<'PY'
from stock_research.daily_close_pipeline import PipelineConfig, parse_trade_date
config = PipelineConfig()
print(parse_trade_date(None, config.timezone).isoformat())
PY
)"
fi

ENRICH_START_DATE="${PLATFORM_READY_ENRICH_START_DATE:-$("$PYTHON" - <<PY
from datetime import date, timedelta
print((date.fromisoformat("$TRADE_DATE") - timedelta(days=14)).isoformat())
PY
)}"

LHB_CASE_PATH="${PLATFORM_READY_LHB_CASE_PATH:-$OUTPUT_DIR/dragon_case_curated_library_failure_v2_1.csv}"
LHB_FEATURES_PATH="${PLATFORM_READY_LHB_FEATURES_PATH:-$OUTPUT_DIR/lhb_risk_feature_case_detail_v2_1.csv}"
LHB_ALIGNMENT_PATH="${PLATFORM_READY_LHB_ALIGNMENT_PATH:-$OUTPUT_DIR/dragon_case_lhb_alignment_audit_2024_2026.csv}"

mkdir -p "$LOG_DIR" "$OUTPUT_DIR" "$REPORTS_DIR" "$(dirname "$RUN_LOG")"

run_step() {
  echo "platform_ready_build|step|$1|start|$(date '+%Y-%m-%d %H:%M:%S %z')"
  shift
  "$@"
  echo "platform_ready_build|step|done|$(date '+%Y-%m-%d %H:%M:%S %z')"
}

{
  echo "=== platform ready build start: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
  echo "trade_date=$TRADE_DATE"
  cd "$ROOT"

  run_step public_news_refresh "$PYTHON" - <<'PY'
from stock_research.public_news.service import refresh_public_news_for_dashboard
print(refresh_public_news_for_dashboard())
PY

  IFS=',' read -r -a enrich_datasets <<< "$ENRICH_DATASETS"
  for dataset in "${enrich_datasets[@]}"; do
    run_step "free_enrichment_$dataset" "$PYTHON" -m stock_research.cli free-enrichment-backfill \
      --dataset "$dataset" \
      --start-date "$ENRICH_START_DATE" \
      --end-date "$TRADE_DATE" \
      --output-dir "$OUTPUT_DIR/free_enrichment_daily/$TRADE_DATE/$dataset" \
      --batch-size 20 \
      --sleep-seconds 0
  done

  run_step daily_factor "$PYTHON" -m stock_research.cli run-daily-factor-pipeline \
    --trade-date "$TRADE_DATE" \
    --reports-dir "$REPORTS_DIR"

  run_step technical_features "$PYTHON" -m stock_research.cli build-technical-features-daily \
    --trade-date "$TRADE_DATE" \
    --adjust-type qfq \
    --build-strategy latest_only

  run_step lhb_shortline "$PYTHON" -m stock_research.cli run-lhb-shortline-daily-v1 \
    --case-path "$LHB_CASE_PATH" \
    --lhb-features-path "$LHB_FEATURES_PATH" \
    --alignment-path "$LHB_ALIGNMENT_PATH" \
    --trade-date "$TRADE_DATE" \
    --build-watchlist-diagnostics \
    --output-dir "$OUTPUT_DIR"

  run_step watchlist_default "$PYTHON" -m stock_research.cli watchlist-build \
    --trade-date "$TRADE_DATE" \
    --watchlist-id default \
    --score-version manual_v1 \
    --top-n 30 \
    --output-dir "$OUTPUT_DIR"

  run_step platform_ready_check "$PYTHON" -m stock_research.platform_ready \
    --trade-date "$TRADE_DATE" \
    --reports-dir "$REPORTS_DIR" \
    --json-output "$OUTPUT_DIR/platform_ready_${TRADE_DATE}.json"

  echo "=== platform ready build end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=0 ==="
} 2>&1 | tee -a "$RUN_LOG"
