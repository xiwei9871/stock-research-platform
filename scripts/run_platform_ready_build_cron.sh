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
SMOKE_ONLY="${PLATFORM_READY_SMOKE_ONLY:-0}"

if [ -z "$TRADE_DATE" ]; then
  TRADE_DATE="$("$PYTHON" -c 'from stock_research.daily_close_pipeline import PipelineConfig, parse_trade_date; config = PipelineConfig(); print(parse_trade_date(None, config.timezone).isoformat())')"
fi

mkdir -p "$LOG_DIR" "$OUTPUT_DIR" "$REPORTS_DIR" "$(dirname "$RUN_LOG")"

source "$ROOT/scripts/stock_cron_guard.sh"
clear_stock_proxy_env
stock_cron_guard_or_exit "$PYTHON" "$TRADE_DATE" "${RESEARCH_SERVICE:-}" >>"$RUN_LOG" 2>&1

ENRICH_START_DATE="${PLATFORM_READY_ENRICH_START_DATE:-$("$PYTHON" -c "from datetime import date, timedelta; print((date.fromisoformat('$TRADE_DATE') - timedelta(days=14)).isoformat())")}"

LHB_CASE_PATH="${PLATFORM_READY_LHB_CASE_PATH:-$OUTPUT_DIR/dragon_case_curated_library_failure_v2_1.csv}"
LHB_FEATURES_PATH="${PLATFORM_READY_LHB_FEATURES_PATH:-$OUTPUT_DIR/lhb_risk_feature_case_detail_v2_1.csv}"
LHB_ALIGNMENT_PATH="${PLATFORM_READY_LHB_ALIGNMENT_PATH:-$OUTPUT_DIR/dragon_case_lhb_alignment_audit_2024_2026.csv}"

STEP_STATUS_SUMMARY=""
FAILED_STEP=""
FAILED_RC=0

run_step() {
  local step_name="$1"
  shift
  echo "platform_ready_build|step|${step_name}|start|$(date '+%Y-%m-%d %H:%M:%S %z')" >>"$RUN_LOG"
  set +e
  "$@" >>"$RUN_LOG" 2>&1
  local rc=$?
  set -e
  if [[ "$rc" -ne 0 ]]; then
    STEP_STATUS_SUMMARY="${STEP_STATUS_SUMMARY}${step_name}=failed(rc=${rc}) "
    FAILED_STEP="$step_name"
    FAILED_RC="$rc"
    echo "platform_ready_build|step|${step_name}|failed|rc=${rc}|$(date '+%Y-%m-%d %H:%M:%S %z')" >>"$RUN_LOG"
    return "$rc"
  fi
  STEP_STATUS_SUMMARY="${STEP_STATUS_SUMMARY}${step_name}=success "
  echo "platform_ready_build|step|${step_name}|done|$(date '+%Y-%m-%d %H:%M:%S %z')" >>"$RUN_LOG"
}

run_required_step() {
  set +e
  run_step "$@"
  local rc=$?
  set -e
  if [[ "$rc" -ne 0 ]]; then
    print_summary "平台就绪构建失败"
    exit "$rc"
  fi
}

extract_platform_status() {
  grep -E '平台数据状态：' "$RUN_LOG" | tail -n 1 | sed -E 's/.*平台数据状态：//' || true
}

print_summary() {
  local title="$1"
  echo "$title"
  echo "交易日: $TRADE_DATE"
  local platform_status
  platform_status="$(extract_platform_status)"
  if [[ -n "$platform_status" ]]; then
    echo "平台状态: $platform_status"
  fi
  if [[ -n "$STEP_STATUS_SUMMARY" ]]; then
    echo "步骤: ${STEP_STATUS_SUMMARY% }"
  fi
  if [[ -n "$FAILED_STEP" ]]; then
    echo "失败步骤: $FAILED_STEP"
    echo "退出码: $FAILED_RC"
  fi
  echo "详细日志: $RUN_LOG"
}

if [ "$SMOKE_ONLY" = "1" ]; then
  {
    echo "=== platform ready build smoke start: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
    echo "trade_date=$TRADE_DATE"
    cd "$ROOT"
    "$PYTHON" -c "import stock_research.platform_ready; import stock_research.cli; print('platform_ready_build|smoke|imports_ok')"
    echo "platform_ready_build|smoke|would_run|public_news_refresh"
    echo "platform_ready_build|smoke|would_run|free_enrichment|datasets=$ENRICH_DATASETS|start_date=$ENRICH_START_DATE|end_date=$TRADE_DATE"
    echo "platform_ready_build|smoke|would_run|daily_factor"
    echo "platform_ready_build|smoke|would_run|technical_features"
    echo "platform_ready_build|smoke|would_run|lhb_shortline"
    echo "platform_ready_build|smoke|would_run|watchlist_default"
    echo "platform_ready_build|smoke|would_run|finalize_market_monitor"
    echo "platform_ready_build|smoke|would_run|finalize_deps"
    echo "platform_ready_build|smoke|would_run|finalize_health"
    echo "platform_ready_build|smoke|would_run|strategy_daily_eod"
    echo "platform_ready_build|smoke|would_run|platform_ready_check"
    echo "=== platform ready build smoke end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=0 ==="
  } 2>&1 | tee -a "$RUN_LOG"
  exit 0
fi

echo "=== platform ready build start: $(date '+%Y-%m-%d %H:%M:%S %z') ===" >>"$RUN_LOG"
echo "trade_date=$TRADE_DATE" >>"$RUN_LOG"
cd "$ROOT"

run_required_step public_news_refresh "$PYTHON" -c "from stock_research.public_news.service import refresh_public_news_for_dashboard; print(refresh_public_news_for_dashboard())"

IFS=',' read -r -a enrich_datasets <<< "$ENRICH_DATASETS"
for dataset in "${enrich_datasets[@]}"; do
  run_required_step "free_enrichment_$dataset" "$PYTHON" -m stock_research.cli free-enrichment-backfill \
    --dataset "$dataset" \
    --start-date "$ENRICH_START_DATE" \
    --end-date "$TRADE_DATE" \
    --output-dir "$OUTPUT_DIR/free_enrichment_daily/$TRADE_DATE/$dataset" \
    --batch-size 20 \
    --sleep-seconds 0
done

run_required_step daily_factor "$PYTHON" -m stock_research.cli run-daily-factor-pipeline \
  --trade-date "$TRADE_DATE" \
  --reports-dir "$REPORTS_DIR"

run_required_step technical_features "$PYTHON" -m stock_research.cli build-technical-features-daily \
  --trade-date "$TRADE_DATE" \
  --adjust-type qfq \
  --build-strategy latest_only

run_required_step lhb_shortline "$PYTHON" -m stock_research.cli run-lhb-shortline-daily-v1 \
  --case-path "$LHB_CASE_PATH" \
  --lhb-features-path "$LHB_FEATURES_PATH" \
  --alignment-path "$LHB_ALIGNMENT_PATH" \
  --trade-date "$TRADE_DATE" \
  --build-watchlist-diagnostics \
  --output-dir "$OUTPUT_DIR"

run_required_step watchlist_default "$PYTHON" -m stock_research.cli watchlist-build \
  --trade-date "$TRADE_DATE" \
  --watchlist-id default \
  --score-version manual_v1 \
  --top-n 30 \
  --output-dir "$OUTPUT_DIR"

run_required_step finalize_market_monitor "$PYTHON" -m scripts.daily_pipeline \
  --date "$TRADE_DATE" \
  --stage market_monitor

run_required_step finalize_deps "$PYTHON" -m scripts.daily_pipeline \
  --date "$TRADE_DATE" \
  --stage deps

run_required_step finalize_health "$PYTHON" -m scripts.daily_pipeline \
  --date "$TRADE_DATE" \
  --stage health

run_required_step strategy_daily_eod "$PYTHON" -m stock_research.cli run-strategy-daily-eod \
  --trade-date "$TRADE_DATE" \
  --output-root "$OUTPUT_DIR/strategy_daily_eod"

run_required_step platform_ready_check "$PYTHON" -m stock_research.platform_ready \
  --trade-date "$TRADE_DATE" \
  --reports-dir "$REPORTS_DIR" \
  --json-output "$OUTPUT_DIR/platform_ready_${TRADE_DATE}.json"

echo "=== platform ready build end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=0 ===" >>"$RUN_LOG"
print_summary "平台就绪构建完成"
