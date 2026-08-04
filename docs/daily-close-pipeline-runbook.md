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

## Rolling Oversold Market-Bar Backfill

Rolling-sector oversold research uses a separate, resumable backfill command for
explicit gaps. It does not discover a universe and it does not fall back to a
second data provider inside the strategy. First generate or review the Task1
gap-workplan, then run a dry-run against the same database service:

```bash
PYTHONPATH=src .venv/bin/python -m stock_research.cli \
  rolling-sector-oversold-backfill \
  --dataset market_daily_bar \
  --gap-workplan artifacts/rolling_sector_oversold/gap_workplan_2026-07-21/gap_workplan.json \
  --start-date 2026-07-21 \
  --end-date 2026-07-31 \
  --adjust-types raw,qfq,hfq \
  --source akshare \
  --service stock_research \
  --dry-run \
  --output-dir outputs/research/rolling_sector_oversold_backfill
```

When the AkShare endpoint is unavailable, use the approved Baostock range
adapter instead:

```bash
PYTHONPATH=src .venv/bin/python -m stock_research.cli \
  rolling-sector-oversold-backfill \
  --dataset market_daily_bar \
  --gap-workplan artifacts/rolling_sector_oversold/gap_workplan_2026-07-21/gap_workplan.json \
  --start-date 2026-07-21 \
  --end-date 2026-07-31 \
  --adjust-types raw,qfq,hfq \
  --source baostock \
  --service stock_research \
  --dry-run
```

Both range adapters batch requests by eligible asset and contiguous date range;
they do not issue one external request for every asset/date pair. Baostock uses
`adjustflag=3/2/1` for `raw/qfq/hfq` and records the endpoint and requested
range in the raw payload audit.

Only after reviewing the JSON/CSV report should an operator repeat the command
with `--execute`. The executor queries `core.asset_master` before making any
source request, applies list/delist PIT checks, and never requests BSE (`CN:BJ`)
or other out-of-scope exchanges. `--include-invalid-assets` is reserved for an
explicit historical repair where the operator has accepted those PIT checks.

Each successful row writes both the canonical `market_daily_bar` record and a
raw payload audit record. The conflict keys are
`(asset_id, trade_date, adjust_type)` for market bars and
`(source_service, source_table, adjust_type, trade_date, asset_id)` for raw
payloads, so rerunning the same workplan is idempotent. Reports retain source,
endpoint, requested date range, payload hash, attempts, and per-row status. A
`missing` or `retryable_failure` row is reported for later retry; it is never
filled with zero values. `out_of_scope_bse` rows are reported but are never
sent to an external source.

## Rolling Oversold 302-Concept Membership Backfill (P0)

The frozen 302-concept `ths` target has a separate membership repair command.
It fetches the THS board list once and requests constituents only for target
codes present in the supplied CSV/list. Constituents use the paginated THS
full-page detail endpoint (`ths:q.10jqka.com.cn_gn_detail`, URL
`q.10jqka.com.cn/gn/detail/board/0/field/199112/page/{page}/code/{code}/`)
with the AkShare-bundled `v` cookie. The historical membership contract is the
first 50 source members per concept (`source_member_cap=50`), matching the
existing core membership/market-bar universe; the adapter stops after page 5
when that cap is reached and records the concept in
`member_cap_applied_concepts`. This is an explicit contract, not an unreported
truncation. Boards with fewer than 50 members are read to their reported final
page. The EastMoney/AkShare adapter is available only as an explicit fallback
function.
The strategy itself remains database-only and never calls this source boundary.

The THS detail URL is a live current ranking sorted by `field=199112`
(`涨跌幅`) and exposes no provider-side effective-date parameter. For strict
historical work the default adapter reports
`source_pit_status=current_unknown_asof` and remains write-blocked. For the
daily research workflow, the explicitly enabled `--assume-daily-snapshot-pit`
policy treats a successfully captured snapshot on `--trade-date` as the
latest PIT snapshot for that date. The report records
`source_pit_status=assumed_daily_snapshot` and
`source_kind=ths_assumed_daily_snapshot`; this is an operational assumption,
not a claim that the provider supplied a historical timestamp.

Preview first (the CLI defaults to `--dry-run`):

```bash
PYTHONPATH=src .venv/bin/python -m stock_research.cli \
  rolling-sector-target-membership-backfill \
  --trade-date 2026-07-31 \
  --concept-codes-file outputs/research/concept_drawdown_over24_2026-08-01.csv \
  --service stock_research \
  --output-dir outputs/research/rolling_sector_target_membership_backfill \
  --dry-run
```

Review `target_membership_backfill_summary.json` before executing. The report
and CSV retain `source_asof`, `source_effective_date`, `source_pit_status`,
`source_missing_codes`, `failed_concepts`, `out_of_scope_bse`, and
`out_of_scope_900xxx`; a failed or empty source response is never allowed to
close its prior active membership history. Only active-at-cutoff,
non-delisted, non-BSE assets present in `core.asset_master` are valid. A
`900xxx` B-share code is explicitly audited and excluded rather than silently
dropped. Strict historical writes additionally require an explicit source
effective date no later than the requested trade date. Missing metadata
reports `write_blocked_reason=source_asof_unknown`; a later effective date
reports `write_blocked_reason=source_asof_after_requested_date`. With
`--assume-daily-snapshot-pit`, a partial live snapshot may write only the
successful concepts; failed or missing concepts remain untouched and are
listed in `failed_concepts`/`source_missing_codes`.
For each successful concept, the current cutoff snapshot is upserted first and
then every older active membership row (`start_date < trade_date`) is closed at
the cutoff; this deliberately removes stale duplicate active rows while
leaving failed or missing concepts untouched.
`--execute` only enables writes after the selected policy gates pass. Without
`--assume-daily-snapshot-pit`, it does not override unknown source dates. Board
and membership writes then share one database transaction, with the membership
conflict key
`(asset_id, concept_system, concept_code, start_date)`, so an identical rerun
is idempotent. `database_writes` is always zero in a dry-run.

For the daily operational snapshot, run:

```bash
PYTHONPATH=src .venv/bin/python -m stock_research.cli \
  rolling-sector-target-membership-backfill \
  --trade-date 2026-08-04 \
  --concept-codes-file outputs/research/concept_drawdown_over24_2026-08-01.csv \
  --service stock_research \
  --output-dir outputs/research/rolling_sector_target_membership_2026-08-04 \
  --assume-daily-snapshot-pit \
  --execute
```

When a provider supplies a dated export, pass it explicitly with
`--membership-snapshot-file`. CSV, JSON, and Parquet are accepted. The file
must contain `concept_code`, `concept_name`, and `asset_id`, plus one uniform
`source_asof` (or `source_effective_date`) no later than `--trade-date`; every
target concept must have at least one row. Duplicate concept/member pairs,
outside-target codes, missing names, invalid asset IDs, and mixed or unknown
effective dates fail closed before any source fetch or database write. A JSON
object may use a top-level `source_asof` and a `rows`/`memberships` array. The
report records `source_kind`, `membership_snapshot_file`, and
`snapshot_payload_sha256` for lineage. Example:

```bash
PYTHONPATH=src .venv/bin/python -m stock_research.cli \
  rolling-sector-target-membership-backfill \
  --trade-date 2026-07-31 \
  --concept-codes-file outputs/research/concept_drawdown_over24_2026-08-01.csv \
  --membership-snapshot-file /path/to/ths_memberships_2026-07-31.csv \
  --service stock_research \
  --output-dir outputs/research/rolling_sector_target_membership_backfill \
  --dry-run
```

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
