# P3 Scope Freeze

Date: 2026-05-29

## Status

P3 scope is frozen around **Read Model + Operator Dashboard Prep**.

P3 starts after:

- P2 completion review:
  - `docs/quant_system/16_p2_completion_review.md`
- P2 daily runbook and operational smoke:
  - `docs/quant_system/17_p2_daily_runbook_and_smoke_report.md`
- P2 durable storage decision:
  - `docs/quant_system/15_p2_durable_storage_decision.md`

## Why This Scope

P2 proved the file-based review flow:

1. `p2-simulation-review`
2. `p2-artifact-rollup`
3. `p2-aggregate-review`

The next bottleneck is not UI polish. It is queryability: operators will need to ask
questions across days, statuses, blockers, portfolios, risk levels, and artifact paths
without scanning local JSON and Markdown files manually.

P3 therefore builds stable read models first. A dashboard can consume those read models
later without forcing UI decisions into schema and ingestion work.

## P3 In Scope

### P3-1 P2 Review Read Model Schema

Goal: persist compact, queryable P2 aggregate review metadata.

Deliver:

- Schema for aggregate review runs.
- Schema for aggregate review sections.
- Tests proving the DDL includes the expected tables, keys, and indexes.
- No raw source artifact duplication.

Candidate tables:

- `ops.p2_review_run`
- `ops.p2_review_section`

Boundary:

- Store summary/read-model fields only.
- Keep generated P2 JSON/Markdown artifacts as the audit source.
- Do not store webhook URLs, credentials, tokens, or broker/account data.

Implementation status: implemented and ready for review.

Delivered:

- `ops.p2_review_run`
- `ops.p2_review_section`
- Schema tests:
  - `tests/test_schema.py::test_research_extension_includes_p2_review_read_model_tables`

### P3-2 P2 Review Import / Backfill CLI

Goal: import existing P2 aggregate review JSON files into the read model.

Deliver:

- Parser for `p2_aggregate_review_<trade_date>.json`.
- Idempotent upsert helpers.
- CLI command to import one file or a directory of files.
- Tests for parse, upsert SQL parameters, idempotent conflict behavior, and CLI output.

Boundary:

- Do not require a scheduler.
- Do not require a Web app.
- Do not mutate the original generated artifacts.

Implementation status: implemented and ready for review.

Delivered:

- `stock_research.p2.review_read_model.load_p2_aggregate_review_rows`
- `stock_research.p2.review_read_model.import_p2_aggregate_review`
- CLI command:
  - `p3-import-p2-aggregate-review`
- Module tests:
  - `tests/test_p2_review_read_model.py`
- CLI tests:
  - `tests/test_factor_cli.py -k p3_import_p2_aggregate_review`

### P3-3 Virtual Portfolio Read Model Schema

Goal: persist compact virtual portfolio state history for cross-day risk review.

Deliver:

- Schema for daily virtual portfolio state.
- Optional schema for daily virtual portfolio positions if the P2 smoke / review flow
  proves position-level queries are needed.
- Tests proving table definitions, keys, and indexes.

Candidate tables:

- `simulation.virtual_portfolio_state_daily`
- `simulation.virtual_portfolio_position_daily`

Boundary:

- These are simulated/review-only portfolio tables.
- Do not add broker orders, executions, account balances, or live position tables.
- Do not infer real holdings from virtual portfolio output.

### P3-4 Virtual Portfolio Import / Backfill CLI

Goal: import P2 virtual portfolio review JSON and CSV artifacts into the read model.

Deliver:

- Parser for `virtual_portfolio_review_<trade_date>_<portfolio_id>.json`.
- Optional CSV import for history and latest positions.
- Idempotent upsert helpers.
- CLI command to import one file or a directory of files.
- Tests for risk summary preservation and source artifact path preservation.

Boundary:

- Keep `manual_review_required` semantics intact.
- Keep `auto_trade_enabled = false` in every trading-adjacent output.
- Do not create advice execution or order lifecycle tables.

### P3-5 Operator Query Export

Goal: provide dashboard-ready JSON/CSV exports before building a dashboard.

Deliver:

- CLI command to query recent P2 review runs.
- CLI command or option to export latest review status by trade date.
- JSON/CSV output for:
  - run status
  - blocker count
  - warning count
  - section status
  - portfolio risk level
  - source artifact paths
- Tests for filtering by date, status, section group, and portfolio.

Boundary:

- This is not a Web dashboard.
- Output is a stable API-like export for future dashboard consumption.

## Out Of Scope For P3

- Live trading.
- Broker adapters.
- Automatic order placement.
- Real order, execution, account, or cash ledger tables.
- Complex Web dashboard implementation.
- Rewriting P2 artifact contracts.
- Replacing existing report delivery, agent, factor, simulation, or watchlist flows.

## Execution Order

1. P3-0: confirm workspace is clean and preserve P2 smoke evidence.
2. P3-1: add aggregate review read model schema.
3. P3-2: import/backfill aggregate review artifacts.
4. P3-3: add virtual portfolio read model schema.
5. P3-4: import/backfill virtual portfolio artifacts.
6. P3-5: add operator query/export commands.
7. P3 review: decide whether P4 should be dashboard UI or scheduler integration.

## Acceptance Criteria

P3 is ready for review when:

- P2 aggregate review JSON can be imported into durable read-model tables.
- Virtual portfolio review artifacts can be imported into durable read-model tables.
- Imports are idempotent.
- Source artifact paths are preserved.
- Query/export commands can answer daily operator questions without scanning files.
- Generated artifacts remain the audit source.
- No trading automation or broker integration is introduced.
- `.venv/bin/pytest -q` passes.

## Safety Rules

- Read models must not become the only audit trail.
- Every imported row must preserve a source artifact path.
- Every trading-adjacent row remains simulation/review-only.
- No secret, token, webhook URL, broker credential, account number, or order payload
  may be persisted.
- Any future dashboard must be read-only unless a separate safety design is approved.

## First Implementation Target

Start with P3-1 and P3-2 together:

- add `ops.p2_review_run`
- add `ops.p2_review_section`
- add a focused aggregate review importer
- add a CLI for importing one aggregate review JSON file

This is the narrowest useful slice because it immediately turns the P2 aggregate review
artifact into a queryable operational record while leaving simulation-specific tables
for the next slice.
