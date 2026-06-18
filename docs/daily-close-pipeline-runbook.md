# Daily Close Pipeline Runbook

This pipeline updates A-share data after market close without BaoStock.

## Environment

Set these variables in the cron/systemd environment or shell:

```bash
export TUSHARE_TOKEN=...
export DB_SERVICE=stock_research
export PIPELINE_TIMEZONE=Asia/Shanghai
export DAILY_START_TIME=17:00
export MINUTE5_START_TIME=17:30
export DEPS_START_TIME=19:00
export FINALIZE_TIME=19:50
export MAX_WORKERS_DAILY=8
export MAX_WORKERS_MINUTE5=8
export REQUEST_TIMEOUT_SECONDS=20
export MAX_RETRIES=3
export MINUTE5_LOOKBACK_DAYS=5
export MINUTE5_MIN_COVERAGE_RATIO=0.98
export PIPELINE_FORCE_NON_TRADING_DAY=false
```

`TUSHARE_TOKEN` can also be read from `config/local_secrets.json` under
`{"tushare": {"token": "..."}}`.

## Schema

The CLI applies the pipeline schema before running. The same SQL is available at
`deploy/daily_close_pipeline.sql` for manual review or DBA-managed deployment.
Tables are created under `ops`:

- `ops.daily_pipeline_job`
- `ops.daily_pipeline_quality`
- `ops.daily_pipeline_failed_symbol`
- `ops.daily_pipeline_status`

## Cron

Install a crontab similar to:

```cron
0 17 * * 1-5 cd /Users/xiwei/stock_research && .venv/bin/python -m scripts.daily_pipeline --stage daily
30 17 * * 1-5 cd /Users/xiwei/stock_research && .venv/bin/python -m scripts.daily_pipeline --stage minute5
0 19 * * 1-5 cd /Users/xiwei/stock_research && .venv/bin/python -m scripts.daily_pipeline --stage deps
50 19 * * 1-5 cd /Users/xiwei/stock_research && .venv/bin/python -m scripts.daily_pipeline --stage health
```

Holiday/non-trading-day filtering uses `market.trading_calendar` as the formal
gate. When the calendar has rows for the date and all relevant exchanges are
closed, source requests are skipped and the platform remains available on the
latest ready trade date. If the date is missing from the calendar, the pipeline
treats it as `unknown` and continues so an incomplete calendar does not block
initial operations.

## Manual Runs

```bash
.venv/bin/python -m scripts.daily_pipeline --date 20260605 --stage all
.venv/bin/python -m scripts.daily_pipeline --date 20260605 --stage daily
.venv/bin/python -m scripts.daily_pipeline --date 20260605 --stage minute5
.venv/bin/python -m scripts.daily_pipeline --date 20260605 --stage retry_failed
.venv/bin/python -m scripts.daily_pipeline --date 20260605 --stage status
```

Use `--force` to manually backfill a date that the calendar marks as closed:

```bash
.venv/bin/python -m scripts.daily_pipeline --date 20260606 --stage all --force
```

The same command is available through the project CLI:

```bash
.venv/bin/stock-research daily-pipeline --date 20260605 --stage status
```

## Logs And Status

Stage logs are written to `logs/pipeline/YYYYMMDD/<stage>.log`.

Check platform readiness through:

```bash
.venv/bin/python -m scripts.daily_pipeline --date 20260605 --stage status
curl http://127.0.0.1:8765/api/data/status
```

`READY` means core data finished. `DEGRADED_READY` means core data is usable
with partial or optional failures. `NOT_READY` means strategies should fall
back to the latest ready trade date.
