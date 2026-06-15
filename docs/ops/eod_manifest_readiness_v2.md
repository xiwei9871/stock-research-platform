# EOD Manifest And Readiness V2

## Scope

Batch A closes the local EOD research baseline around operational state:

- record each EOD module in a normalized manifest;
- upgrade `run-stock-daily-data-pipeline` `run_summary.json`;
- make `/api/platform/readiness` prefer manifest and summary evidence;
- classify readiness as `OK`, `PARTIAL`, or `BLOCKED`;
- keep the dashboard and strategy logic stable.

This batch does not add strategies, data sources, trading execution, broker
integration, SaaS behavior, or major frontend layout changes.

## Current State

The repository already has:

- `src/stock_research/daily_data_pipeline.py`, which orchestrates EOD steps and
  writes `run_summary.json`;
- `src/stock_research/daily_job_run_store.py`, which writes coarse
  `ops.daily_job_run` records;
- `src/stock_research/dashboard/readiness.py`, which probes platform summary,
  TopN, news, research reports, and generated reports;
- `GET /api/platform/readiness`, exposed by the dashboard API;
- focused pytest and Playwright coverage for readiness and the dashboard.

The gap is that readiness does not consume the daily run state, and the existing
`run_summary.json` does not expose tier status, module status, run lineage, or
machine-readable next actions.

## Data Model

Keep `ops.daily_job_run` as the low-level historical step record used by older
P4/P19 flows. Add `ops.data_run_manifest` as the normalized EOD module manifest
for Batch A.

`ops.daily_job_run` remains:

- coarse step status;
- backward compatible;
- not the primary readiness source.

`ops.data_run_manifest` is:

- one row per run/module/source;
- explicit tier/status/row-count/freshness/artifact metadata;
- the primary database source for readiness v2.

Required columns:

- `manifest_id text primary key`
- `run_id text not null`
- `run_date date not null`
- `trade_date date`
- `module text not null`
- `source text not null`
- `tier text not null check (tier in ('tier1', 'tier2', 'tier3'))`
- `status text not null check (status in ('success', 'partial', 'skipped', 'failed', 'unavailable'))`
- `started_at timestamptz`
- `ended_at timestamptz`
- `duration_seconds numeric`
- `row_count bigint`
- `asset_count bigint`
- `coverage_ratio numeric`
- `latest_trade_date date`
- `freshness_lag integer`
- `warning_count integer not null default 0`
- `warnings jsonb not null default '[]'::jsonb`
- `error_message text`
- `artifact_path text`
- `code_version text`
- `config_version text`
- `metadata jsonb not null default '{}'::jsonb`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

The manifest service will also support local JSON output. The daily pipeline can
write manifest rows to `run_manifest.json` even when database writes are
disabled or unavailable.

## Tier Definition

Tier 1 blocks the EOD baseline if failed:

- `assets_universe`
- `trading_calendar`
- `daily_bars`
- `factor_pipeline`
- `score_topn`
- `review_queue`

Tier 2 makes readiness partial if failed:

- `news`
- `research_reports`
- `lhb`
- `industry`
- `financial`
- `technical_features`
- `generated_reports`

Tier 3 is non-blocking and warning-only:

- `intraday`
- `minute_bars`
- `auction`
- `experimental_enrichment`

Modules that are not wired in the current EOD pipeline are recorded as
`skipped` or `unavailable`; this batch does not create new collectors.

## Status Rules

Module statuses:

- `success`: module completed and produced usable evidence;
- `partial`: module produced usable but incomplete evidence;
- `skipped`: intentionally not run in this local EOD path;
- `failed`: attempted and failed;
- `unavailable`: no stable local pipeline or source state exists yet.

Tier status:

- `OK`: all required modules in the tier are `success` or explicitly acceptable
  `skipped`;
- `PARTIAL`: at least one module is `partial`, `failed`, or `unavailable`, but
  no Tier 1 blocker exists;
- `BLOCKED`: any Tier 1 required module is `failed`, `unavailable`, or missing,
  or score/TopN/Review Queue is unavailable.

Overall summary/readiness status:

- `OK`: Tier 1 is OK and Tier 2/Tier 3 have no warnings;
- `PARTIAL`: Tier 1 is OK and Tier 2/Tier 3 are partial;
- `BLOCKED`: Tier 1 is blocked.

## Readiness Rules

Readiness v2 prefers the latest daily summary or manifest by `run_id` and
`trade_date`.

If a summary/manifest exists:

- compute tier status from manifest modules;
- verify latest trade date;
- verify score/TopN via platform summary;
- verify Review Queue with a bounded probe;
- classify news/research reports/generated reports as Tier 2 partial if absent;
- return warnings, errors, missing data, partial data, and next actions.

If no summary/manifest exists:

- fall back to the current lightweight probes;
- return `BLOCKED` when Tier 1 evidence is missing;
- return a next action instructing the operator to run the EOD pipeline.

## Daily Summary JSON

`run_summary.json` will be upgraded to this machine-readable shape:

```json
{
  "run_id": "eod-2026-06-12-local",
  "run_date": "2026-06-15",
  "latest_market_date": "2026-06-12",
  "started_at": "2026-06-15T20:00:00+08:00",
  "ended_at": "2026-06-15T20:10:00+08:00",
  "status": "PARTIAL",
  "tier1_status": "OK",
  "tier2_status": "PARTIAL",
  "tier3_status": "PARTIAL",
  "modules": [],
  "assets_count": 5200,
  "daily_bar_rows": 5200,
  "factor_rows": 218400,
  "score_version": "manual_v1",
  "topn_generated": true,
  "topn_count": 30,
  "review_queue_count": 20,
  "evidence_digest_count": 0,
  "news_count": 120,
  "report_count": 12,
  "lhb_count": 80,
  "warning_count": 2,
  "warnings": [],
  "errors": [],
  "artifacts": {},
  "readiness_status": "PARTIAL",
  "dashboard_readiness_url": "http://127.0.0.1:8765/api/platform/readiness"
}
```

The existing `steps` field may remain for backward compatibility, but consumers
should prefer `modules`.

## API Response Shape

`GET /api/platform/readiness` returns:

```json
{
  "mode": "eod_local",
  "status": "PARTIAL",
  "as_of": "2026-06-15T20:11:00+08:00",
  "run_id": "eod-2026-06-12-local",
  "latest_trade_date": "2026-06-12",
  "latest_market_date": "2026-06-12",
  "source": "data_run_manifest",
  "summary_path": "outputs/research/stock_daily_data_pipeline/2026-06-12/run_summary.json",
  "tiers": [],
  "modules": [],
  "warnings": [],
  "errors": [],
  "missing_data": [],
  "partial_data": [],
  "next_actions": [],
  "dashboard_url": "http://127.0.0.1:5174"
}
```

Keep `latest_market_date` for frontend compatibility while adding
`latest_trade_date`.

## Test Plan

Focused tests:

- manifest schema DDL includes `ops.data_run_manifest`;
- manifest write/read handles `success`, `failed`, `partial`, and `skipped`;
- daily pipeline writes v2 `run_summary.json`;
- readiness returns `OK` when Tier 1 and optional modules are healthy;
- readiness returns `PARTIAL` when Tier 2 fails;
- readiness returns `BLOCKED` when Tier 1 fails;
- missing TopN returns `BLOCKED`;
- news/research report absence returns `PARTIAL` with warnings;
- `/api/platform/readiness` response includes v2 fields;
- daily pipeline smoke still passes.

## Smoke Test

After implementation:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_data_run_manifest.py \
  tests/test_daily_data_pipeline.py \
  tests/test_dashboard_readiness.py \
  tests/test_dashboard_app.py \
  -q

cd dashboard
pnpm test -- --run tests/client.test.ts tests/home-cockpit.test.tsx
pnpm build
pnpm exec playwright test tests/platform-full-flow.spec.ts
```

## Later Batches

Batch B can use the v2 response to reorganize Home without changing the
readiness contract. Batch C can add score/factor/strategy governance registries.
Batch D can classify experimental and legacy modules without changing the EOD
manifest model.
