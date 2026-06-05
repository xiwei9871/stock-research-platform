# Stock Daily Data Pipeline Runbook

## Dry Run Without Feishu

Use this command for a local smoke run that writes artifacts without sending a Feishu message:

```bash
cd /Users/xiwei/stock_research
./.venv/bin/python -m stock_research.cli run-stock-daily-data-pipeline \
  --trade-date 2026-06-05 \
  --output-dir outputs/research/stock_daily_data_pipeline_smoke/2026-06-05 \
  --no-feishu
```

When `--no-feishu` is used, the `daily_report_delivery` step can have `status=skipped`.

## Live Host Script

Use the host script for the scheduled live run:

```bash
STOCK_DAILY_PIPELINE_TRADE_DATE=2026-06-05 \
STOCK_DAILY_PIPELINE_FEISHU_TARGET=chat:oc_82dd978138a0cde5864868c5b5b8e754 \
/Users/xiwei/stock_research/scripts/run_stock_daily_data_pipeline.sh
```

## Outputs

- `run_summary.json`
- `feishu_message.txt`
- `logs/stock_daily_data_pipeline.host.log`
- step-specific output directories under `outputs/research/stock_daily_data_pipeline/<trade_date>`

## Healthy Run

- `run_summary.json` has `status` equal to `success` or `partial_failed`.
- The CLI exits nonzero when the final status is `partial_failed`; inspect the artifacts before retrying because valid step outputs and a Feishu message draft may still have been written.
- Required failed steps appear with `status=failed` and an error field.
- Feishu message includes the trade date, output directory, and every step status.
- No interactive process remains after the host script exits.

## Recovery

If the daily job fails before sending Feishu, OpenClaw `failureAlert` sends a failure notice. Inspect:

```bash
tail -100 /Users/xiwei/stock_research/logs/stock_daily_data_pipeline.host.log
cat /Users/xiwei/stock_research/outputs/research/stock_daily_data_pipeline/<trade-date>/run_summary.json
```
