# Free A-Share Enrichment Data Design

## Goal

Build a free-source enrichment data pipeline for A-share research so the project can ingest 龙虎榜、股东、回购、调研、业绩预告、业绩快报、主营构成 from AkShare-backed public sources before buying additional Tushare permissions.

The first production scope is all listed A-shares from `2025-01-01` through the current run date.

## Current Context

The project already has partial LHB support:

- `market.lhb_top_list_daily`
- `market.lhb_top_inst_daily`
- `factor.lhb_event_features_daily`
- `src/stock_research/lhb_data.py`
- `stock-research lhb-sample-import`

Existing LHB storage is reusable, but historical coverage is thin. The other requested enrichment datasets do not yet have a unified normalized store.

The worktree currently contains many unrelated uncommitted changes, so implementation must keep edits narrow and avoid reverting or rewriting unrelated files.

## Data Sources

Use free public paths exposed through AkShare as the first implementation source. The expected source families are:

- LHB: Eastmoney LHB endpoints through AkShare.
- Shareholder count and holders: Eastmoney shareholder analysis endpoints through AkShare.
- Shareholder or executive trade events: Eastmoney holder trade endpoints through AkShare.
- Repurchase: Eastmoney stock repurchase endpoint through AkShare.
- Institution survey: Eastmoney or CNINFO survey endpoints through AkShare.
- Earnings forecast and express: Eastmoney financial disclosure endpoints through AkShare.
- Main business composition: Eastmoney main business composition endpoint through AkShare.

Each normalized row must include `source`, `source_endpoint`, and a deterministic `payload_hash` or source event key so source drift can be audited later.

## Storage Design

Keep normalized tables separate by data shape instead of forcing all records into one generic event table.

Reuse:

- `market.lhb_top_list_daily`
- `market.lhb_top_inst_daily`

Add normalized tables:

- `fundamental.shareholder_count`
- `fundamental.top10_holder`
- `fundamental.top10_float_holder`
- `event.shareholder_trade`
- `event.stock_repurchase`
- `event.institution_survey`
- `event.earnings_forecast`
- `event.earnings_express`
- `finance.main_business_composition`

Add raw storage:

- `raw_akshare.enrichment_payload`

Raw payload rows must store:

- `source_endpoint`
- `request_params`
- `asset_id`
- `ts_code`
- `payload`
- `payload_hash`
- `fetched_at`

Normalized tables should use stable natural keys where available. If the upstream source does not provide an ID, use a deterministic hash from source endpoint, ts_code, relevant dates, title or event type, and key numeric fields.

## Pipeline Design

Create a focused module:

- `src/stock_research/free_enrichment_data.py`

Each dataset should have the same internal shape:

- `fetch_*_akshare(...)`
- `normalize_*_rows(...)`
- `upsert_*_rows(...)`
- `run_*_backfill(...)`

The CLI entrypoint should be:

```bash
stock-research free-enrichment-backfill \
  --dataset all \
  --start-date 2025-01-01 \
  --end-date today \
  --batch-size 100 \
  --sleep-seconds 1 \
  --output-dir outputs/research/free_enrichment
```

Supported datasets:

- `all`
- `lhb`
- `holder`
- `repurchase`
- `survey`
- `forecast`
- `express`
- `mainbiz`

CLI options:

- `--dataset`
- `--start-date`
- `--end-date`
- `--batch-size`
- `--sleep-seconds`
- `--limit`
- `--dry-run`
- `--output-dir`
- `--service`

## Backfill Strategy

Use the most efficient request pattern per dataset:

- Date-range backfills:
  - LHB
  - repurchase
  - earnings forecast
  - earnings express
- Stock or period backfills:
  - shareholder count
  - top10 holder
  - top10 float holder
  - shareholder trade
  - institution survey
  - main business composition

Batch execution must print progress after each batch:

- dataset name
- current batch number and total batches when known
- processed stock count or date-window count
- fetched rows
- normalized rows
- upserted rows
- empty-result count
- failed count
- failure sample output path

Failures should be captured as data, not swallowed. A failed request should not stop the full run unless the caller passes a strict option in a future extension.

## Output Artifacts

Each run writes:

- `run_summary.json`
- `dataset_coverage.csv`
- `dataset_failures.csv`
- one sample CSV per dataset with the most recent normalized rows

Coverage report columns:

- `dataset`
- `start_date`
- `end_date`
- `asset_count_total`
- `asset_count_covered`
- `coverage_ratio`
- `row_count`
- `empty_result_count`
- `failed_request_count`
- `source`

## Data Quality Rules

Dates must be normalized to ISO `YYYY-MM-DD`.

Stock identity must normalize to both:

- `ts_code`, such as `600000.SH`
- `asset_id`, such as `CN:SH:600000`

Financial and event data must preserve point-in-time dates when available:

- earnings forecast: announcement date and report period
- earnings express: announcement date and report period
- main business composition: report period
- repurchase: announcement date and event/progress date if present
- shareholder records: report date or disclosure date if present

Rows without a valid stock identity should be written to the failure artifact and skipped from normalized upsert.

## Testing Strategy

Use TDD for implementation.

Unit tests should cover:

- stock code normalization
- payload hashing
- empty AkShare responses
- schema creation strings for new tables
- one normalizer test per dataset using small fake AkShare frames
- upsert SQL conflict keys for each normalized table
- CLI argument parsing for dataset selection and dry-run
- run summary generation with success, empty, and failed batches

Integration smoke should run with faked AkShare clients first. Live AkShare runs should be manual commands because public endpoints can change or throttle.

## Rollout Plan

1. Add schema and raw payload table.
2. Extend existing LHB command to support full-range AkShare backfill using current tables.
3. Add holder datasets.
4. Add event datasets: shareholder trade, repurchase, survey.
5. Add earnings forecast and express.
6. Add main business composition.
7. Add coverage report and run summary.
8. Run `2025-01-01` through current date for all A-shares and review coverage.

## Non-Goals

This design does not buy or depend on Tushare permissions.

This design does not parse PDF announcements or broker research PDFs.

This design does not force every event into one generic event table.

This design does not promote these fields directly into production scoring before coverage and stability are measured.

## Open Decisions Resolved

The first implementation uses Scheme A: separate normalized tables plus raw AkShare payload storage.

The first backfill window is all listed A-shares from `2025-01-01` through the current run date.
