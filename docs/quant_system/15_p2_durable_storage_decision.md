# P2 Durable Storage Decision

Date: 2026-05-28

## Decision

P2 should not add new database tables yet.

P2-1 through P2-3 have established file-based contracts for daily artifact rollup,
virtual portfolio review, and aggregate operator review. Those contracts are now good
enough for review and daily operation, but they have not run long enough to justify
locking all fields into relational tables.

The durable storage path is:

1. Keep generated P2 artifacts as the source of truth for the rest of P2.
2. Use existing `report.report_run` only as an optional index for P2 report paths.
3. Promote selected metadata into new tables only after the file contracts prove
   stable across repeated daily runs.
4. Prioritize simulation state and aggregate review metadata if P3 needs cross-day
   querying, dashboard filters, or audit trails.

This preserves P2's boundary: no live trading, no broker adapter, and no automatic
order generation.

## Evaluated Options

### Option A: Add P2 Tables Now

Add dedicated tables for rollups, aggregate reviews, simulation history, and advice
summaries immediately.

Trade-off:

- Pros: easier SQL queries from day one.
- Cons: schema may encode unstable artifact fields too early, creating migration
  churn and slowing review iteration.

Decision: reject for P2-4.

### Option B: Keep P2 File-Only Permanently

Keep all P2 output as JSON, Markdown, and CSV artifacts.

Trade-off:

- Pros: lowest complexity and no migration risk.
- Cons: poor cross-day search, weak dashboard readiness, and harder operational audit.

Decision: reject as a long-term position.

### Option C: File Contracts First, Selective Tables Later

Keep P2 file-based now, then promote only stable, frequently queried summaries into
tables.

Trade-off:

- Pros: preserves implementation speed while leaving a clear path to durable query
  surfaces.
- Cons: requires a later backfill step once table contracts are approved.

Decision: accept.

## Artifact Storage Classification

| P2 artifact | Current source of truth | Durable table decision | Reason |
| --- | --- | --- | --- |
| P2 artifact rollup JSON/Markdown | File artifact | Defer; optional future run/item metadata | Useful for readiness history, but current fields are small and path-based. |
| Virtual portfolio review JSON | File artifact | Candidate for first promotion | Cross-day risk, equity, exposure, and position history will become query-heavy. |
| Virtual portfolio history CSV | File artifact | Candidate for first promotion | Naturally tabular daily state; useful for dashboards and audits. |
| Virtual portfolio positions CSV | File artifact | Candidate after history table | Useful only if position-level review becomes part of repeated operation. |
| P2 aggregate review JSON/Markdown | File artifact | Candidate for compact review-run table | Operator status, blockers, and section status are stable and dashboard-friendly. |
| Agent/watchlist/factor/technical source artifacts | Existing source files | Do not duplicate raw payloads | Preserve paths and summary metadata; avoid copying large or unstable payloads. |

## Proposed Future Schema

This is a proposal only. Do not add it in P2-4.

### `ops.p2_review_run`

Purpose: one row per generated aggregate review.

Suggested columns:

- `run_id text primary key`
- `trade_date date not null`
- `status text not null`
- `source_rollup_status text`
- `artifact_count integer not null default 0`
- `blocker_count integer not null default 0`
- `warning_count integer not null default 0`
- `json_path text not null`
- `markdown_path text not null`
- `metadata jsonb not null default '{}'::jsonb`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

Suggested indexes:

- `(trade_date, updated_at desc)`
- `(status, trade_date desc)`

### `ops.p2_review_section`

Purpose: queryable status for each aggregate review section.

Suggested columns:

- `run_id text not null`
- `section_group text not null`
- `section_name text not null`
- `status text not null`
- `required boolean not null`
- `exists boolean not null`
- `source_artifact_path text not null`
- `summary jsonb not null default '{}'::jsonb`
- `created_at timestamptz not null default now()`
- primary key: `(run_id, section_group, section_name)`

Suggested indexes:

- `(section_group, status)`

### `simulation.virtual_portfolio_state_daily`

Purpose: queryable virtual portfolio state and risk history.

Suggested columns:

- `portfolio_id text not null`
- `trade_date date not null`
- `strategy_id text not null`
- `cash numeric`
- `market_value numeric`
- `equity numeric`
- `drawdown numeric`
- `exposure_pct numeric`
- `open_position_count integer not null default 0`
- `risk_level text`
- `source_artifact_path text not null`
- `created_at timestamptz not null default now()`
- primary key: `(portfolio_id, trade_date, strategy_id)`

Suggested indexes:

- `(portfolio_id, trade_date desc)`
- `(risk_level, trade_date desc)`

### `simulation.virtual_portfolio_position_daily`

Purpose: queryable latest position snapshots for virtual portfolio review.

Suggested columns:

- `portfolio_id text not null`
- `trade_date date not null`
- `strategy_id text not null`
- `asset_id text`
- `stock_code text not null`
- `stock_name text`
- `quantity numeric`
- `market_value numeric`
- `weight numeric`
- `cost_basis numeric`
- `unrealized_pnl numeric`
- `source_artifact_path text not null`
- `created_at timestamptz not null default now()`
- primary key: `(portfolio_id, trade_date, strategy_id, stock_code)`

Suggested indexes:

- `(stock_code, trade_date desc)`
- `(portfolio_id, trade_date desc)`

## Migration Plan

### Stage 0: P2-4 Decision Only

- Do not modify `src/stock_research/schema.py`.
- Do not add migration SQL.
- Keep P2 outputs file-based.
- Preserve source paths in every artifact.

### Stage 1: Optional Report Indexing

If operators need a searchable run index before new P2 tables exist, record P2 aggregate
report paths through the existing `report.report_run` pattern:

- `report_type = "p2_aggregate_review"`
- `status = aggregate_review.status`
- `report_paths = {"json": "...", "markdown": "..."}`
- `metadata = {"run_id": "...", "blocker_count": ..., "warning_count": ...}`

This does not require schema changes.

### Stage 2: Backfill Candidate Tables

Only after repeated daily P2 runs:

1. Add schema tests for the selected tables.
2. Add idempotent DDL to the existing schema management path.
3. Write a backfill command that reads historical P2 artifact files and upserts table
   rows.
4. Verify the table rows reproduce the same aggregate statuses and blocker counts as
   the original JSON artifacts.

### Stage 3: Make Tables Read Models

Once populated, use tables as query/read models only. Generated JSON, Markdown, and CSV
artifacts remain the audit source for each run.

## Promotion Criteria

Add durable P2 tables only when at least one of these is true:

- Operators need cross-day filtering by P2 status, blocker, risk level, or portfolio.
- A Web dashboard requires fast access to review status without scanning files.
- At least five consecutive daily runs have kept the artifact contract stable.
- Manual review needs historical comparison beyond what local JSON/CSV files provide.
- P3 depends on portfolio state history as an input, not only as a report output.

## Explicit Non-Goals

- Do not persist broker orders in P2.
- Do not create real order, execution, or account tables.
- Do not store webhook URLs, credentials, tokens, or OpenClaw/Feishu secrets.
- Do not duplicate complete agent or watchlist raw payloads into durable tables.
- Do not make database rows the only audit trail.

## Next Step

After P2-4, P2 can be considered closed for the first scoped pass. The next work should
start by choosing either:

- P3 dashboard/read-model implementation, if queryability becomes the bottleneck.
- P2 operational hardening, if repeated daily runs reveal artifact contract gaps.
