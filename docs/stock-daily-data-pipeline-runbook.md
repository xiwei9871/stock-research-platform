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
- per-step command logs under `outputs/research/stock_daily_data_pipeline/<trade_date>/logs/`
- step-specific output directories under `outputs/research/stock_daily_data_pipeline/<trade_date>`

`run_summary.json` is updated while the task is running. If a command is still active,
the current step appears with `status=running` and a `log_path`.

## Step Layout

The market refresh is split into small required steps:

- `sync_core_assets`
- `load_market_bars`
- `check_market_data_freshness`
- `build_asset_status`
- `sync_index_bars`
- `sync_index_constituents`
- `sync_industry_memberships`
- `build_industry_bars`

After those complete, the pipeline runs:

- `minute_incremental_refresh`
- `intraday_feature_build`
- `daily_event_refresh`
- `daily_feature_build`
- `label_incremental_refresh`
- `daily_report_delivery`

`intraday_feature_build` builds `factor.stock_intraday_features_daily` and
`factor.industry_intraday_features_daily` from same-day 5-minute raw bars. It is
not a required step in the daily pipeline while the feature layer is being
validated.

`label_incremental_refresh` runs `compute_labels` with a 90-day window and is not a
required step. If it fails, later required steps are not skipped because of that
failure.

## Intraday Feature Commands

Build one day:

```bash
cd /Users/xiwei/stock_research
./.venv/bin/python -m stock_research.cli build-intraday-features-daily \
  --trade-date 2026-06-05 \
  --freq 5min \
  --adjust-type raw \
  --industry-system csrc
```

Check gaps:

```bash
./.venv/bin/python -m stock_research.cli intraday-feature-gap-check \
  --start-date 2026-06-05 \
  --end-date 2026-06-05 \
  --freq 5min \
  --adjust-type raw
```

Backfill a range:

```bash
./.venv/bin/python -m stock_research.cli backfill-intraday-features-daily \
  --start-date 2025-01-01 \
  --end-date 2026-06-05 \
  --freq 5min \
  --adjust-type raw \
  --industry-system csrc \
  --workers 4 \
  --skip-complete
```

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
ls -lh /Users/xiwei/stock_research/outputs/research/stock_daily_data_pipeline/<trade-date>/logs
```
