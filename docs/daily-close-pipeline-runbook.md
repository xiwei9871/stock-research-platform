# Daily Close Pipeline Runbook

This pipeline updates A-share data after market close. Daily bars use Tushare;
current-day raw 5-minute bars use one serial BaoStock session and qfq 5-minute
bars are derived locally from persisted raw bars and daily adjustment factors.

## Environment

Set these variables in the cron/systemd environment or shell:

```bash
export TUSHARE_TOKEN=...
export DB_SERVICE=stock_research
export PIPELINE_TIMEZONE=Asia/Shanghai
export DAILY_START_TIME=17:00
export MINUTE5_START_TIME=17:00
export DEPS_START_TIME=19:00
export FINALIZE_TIME=19:50
export MAX_WORKERS_DAILY=8
export REQUEST_TIMEOUT_SECONDS=20
export MAX_RETRIES=3
export DAILY_ADJUST_TYPES=raw,qfq,hfq
export MINUTE5_SYMBOL_SLEEP_SECONDS=0.75
export MINUTE5_MIN_COVERAGE_RATIO=0.98
export DAILY_CLOSE_HEARTBEAT_SECONDS=300
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

## Daily Bars

The `daily` stage writes `market_daily_bar` for all configured daily adjust
types. The default is `raw,qfq,hfq`.

- Tushare is the primary source for full-market raw daily bars.
- AkShare is the fallback source for missing `(ts_code, adjust_type)` pairs,
  including `qfq` and `hfq`.
- `ops.daily_pipeline_quality.dataset_name = 'daily_bar'` counts required
  `(ts_code, adjust_type)` pairs, not only stock symbols. With the default
  adjust types, `expected_count` is about three times the active A-share symbol
  count.

## Cron

Install a crontab similar to:

```cron
0 17 * * 1-5 cd /Users/xiwei/stock_research && .venv/bin/python -m scripts.daily_pipeline --stage daily
0 17 * * 1-5 cd /Users/xiwei/stock_research && scripts/run_daily_close_pipeline_cron.sh minute5
0 19 * * 1-5 cd /Users/xiwei/stock_research && .venv/bin/python -m scripts.daily_pipeline --stage deps
50 19 * * 1-5 cd /Users/xiwei/stock_research && .venv/bin/python -m scripts.daily_pipeline --stage health
```

The daily minute5 job requests only the target trading date. On restart it reads
persisted raw quality and fetches only missing or abnormal symbols. The wrapper
emits a compact heartbeat every five minutes while retaining full output in
`logs/cron/`; this keeps OpenClaw's no-output watchdog active without treating a
normal multi-hour BaoStock run as stalled.

OpenClaw command-job settings for the production minute5 task are:

```text
heartbeat interval: 300 seconds
no-output timeout: 1200 seconds
total timeout: 21600 seconds
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

For an operational run with heartbeat and compact summary, prefer:

```bash
TRADE_DATE=2026-06-05 scripts/run_daily_close_pipeline_cron.sh minute5
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
