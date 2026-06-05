#!/usr/bin/env bash
set -euo pipefail

ROOT="${STOCK_DAILY_PIPELINE_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${STOCK_DAILY_PIPELINE_PYTHON:-$ROOT/.venv/bin/python}"
OPENCLAW_BIN="${STOCK_DAILY_PIPELINE_OPENCLAW_BIN:-/Users/xiwei/stock_research/scripts/openclaw_runtime_cli.sh}"
LOG_DIR="${STOCK_DAILY_PIPELINE_LOG_DIR:-$ROOT/logs}"
DEFAULT_RUN_LOG_RELATIVE="logs/stock_daily_data_pipeline.host.log"
RUN_LOG="${STOCK_DAILY_PIPELINE_RUN_LOG:-$LOG_DIR/${DEFAULT_RUN_LOG_RELATIVE#logs/}}"
TRADE_DATE="${STOCK_DAILY_PIPELINE_TRADE_DATE:-$(date +%F)}"
OUTPUT_DIR="${STOCK_DAILY_PIPELINE_OUTPUT_DIR:-$ROOT/outputs/research/stock_daily_data_pipeline/$TRADE_DATE}"
FEISHU_TARGET="${STOCK_DAILY_PIPELINE_FEISHU_TARGET:-chat:oc_82dd978138a0cde5864868c5b5b8e754}"
FEISHU_ACCOUNT="${STOCK_DAILY_PIPELINE_FEISHU_ACCOUNT:-jarvis}"

mkdir -p "$LOG_DIR" "$OUTPUT_DIR"

{
  echo "=== stock daily data pipeline host run start: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
  cd "$ROOT"
  "$PYTHON" -m stock_research.cli run-stock-daily-data-pipeline \
    --trade-date "$TRADE_DATE" \
    --output-dir "$OUTPUT_DIR" \
    --feishu-target "$FEISHU_TARGET" \
    --feishu-account "$FEISHU_ACCOUNT" \
    --openclaw-bin "$OPENCLAW_BIN"
  rc=$?
  echo "=== stock daily data pipeline host run end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ==="
  exit "$rc"
} 2>&1 | tee -a "$RUN_LOG"
