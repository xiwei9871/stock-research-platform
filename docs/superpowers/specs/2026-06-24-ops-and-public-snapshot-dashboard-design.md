# Ops And Public Snapshot Dashboard Design

Date: 2026-06-24

## Goal

Add a website-visible status layer for the A-share platform so the operator can answer, from a browser, whether the daily data workflow started on time, whether it is likely to finish on time, whether intervention is required, and what data is already ready for internal and external consumers.

The design introduces:

- an internal operations page that combines workflow status and data snapshot preview;
- a public read-only snapshot page for a small trusted audience;
- a backend aggregation layer that converts existing pipeline and dashboard sources into two stable read models.

## Problem

The current platform exposes fragments of the truth:

- pipeline readiness exists in `ops.daily_pipeline_status`;
- daily and backfill failures exist in `ops.daily_pipeline_job`, `ops.daily_job_run`, ingest tables, and watchdog logs;
- market state, TopN scores, and reports exist in separate dashboard and reporting flows.

The operator still has to inspect logs, outputs, and tables manually to answer:

- Did the 4:00 workflow start?
- Did the 8:00 deadline slip?
- Is the workflow stuck or only slow?
- Does the issue require intervention?
- What can be safely shown to external readers right now?

## Scope

### In Scope

- Aggregate existing platform state into one internal operations snapshot.
- Aggregate publishable daily outputs into one public snapshot.
- Add three dashboard API endpoints:
  - `GET /api/ops/snapshot`
  - `GET /api/ops/stages`
  - `GET /api/public/snapshot`
- Add one internal dashboard view for operators.
- Add one public read-only dashboard view.
- Keep internal and public access separated by deployment and access control.

### Out Of Scope

- Replacing PostgreSQL with DuckDB.
- Rebuilding current daily and intraday pipelines.
- Exposing raw failures, source outages, or retry details to the public page.
- Adding a full alerting center, per-user permissions matrix, or editable threshold console.

## Users

### Internal Operator

Needs a browser page that answers, in less than 30 seconds:

- whether the workflow started on time;
- whether it is on track;
- whether it is blocked;
- whether intervention is required;
- whether the produced data is already usable.

### External Reader

Needs a read-only public summary that shows only released results:

- latest ready trade date;
- publication state;
- market state summary;
- TopN preview;
- coverage summary.

## Architecture

Use the existing FastAPI dashboard backend and React dashboard frontend. Add one aggregation module in the backend that reads existing platform truth sources and emits two normalized views:

- `internal_ops_snapshot`
- `public_snapshot`

The frontend must consume only these aggregated views for the new pages. It must not compute intervention or readiness rules on the client.

### Existing Sources To Reuse

- `stock_research.daily_close_pipeline.load_data_status_for_dashboard`
- `stock_research.intraday_pipeline.load_intraday_status`
- `stock_research.daily_health.summarize_operational_health`
- `ops.daily_pipeline_status`
- `ops.daily_pipeline_job`
- `ops.daily_job_run`
- existing dashboard loaders for TopN, market state, report links, and public news where useful

### New Backend Unit

Create `src/stock_research/dashboard/ops_snapshot.py` with:

- `build_internal_ops_snapshot(service: str, trade_date: date | None = None) -> dict[str, Any]`
- `load_ops_stage_details(service: str, trade_date: date | None = None) -> list[dict[str, Any]]`
- `build_public_snapshot(service: str, trade_date: date | None = None) -> dict[str, Any]`

This module owns:

- time window interpretation;
- stage rollup;
- heartbeat and stall inference;
- intervention rules;
- public publishability rules;
- fallback behavior when some source tables are empty.

## Read Models

### Internal Ops Snapshot

The internal page reads one object with these sections:

- `run_window`
  - `trade_date`
  - `expected_start_at`
  - `expected_done_by`
  - `started`
  - `started_at`
  - `completed`
  - `completed_at`
  - `on_time`
  - `lateness_minutes`
- `pipeline`
  - `overall_status`
  - `current_stage`
  - `stage_started_at`
  - `stage_elapsed_minutes`
  - `completed_stage_count`
  - `total_stage_count`
  - `progress_pct`
  - `latest_heartbeat_at`
- `health`
  - `heartbeat_fresh`
  - `heartbeat_age_minutes`
  - `stalled`
  - `stalled_reason`
  - `recent_restart_count`
  - `last_error_summary`
- `intervention`
  - `needs_intervention`
  - `severity`
  - `reason_code`
  - `reason_text`
  - `suggested_action`
- `readiness`
  - `latest_ready_trade_date`
  - `ready_status`
  - `ready_for_dashboard`
  - `ready_for_publication`
  - `blocking_issue_count`
- `snapshot_preview`
  - `market_state`
  - `topn_preview`
  - `coverage_summary`
  - `factor_gate_summary`
  - `published_at`

### Public Snapshot

The public page reads one object with these fields:

- `trade_date`
- `published_at`
- `latest_ready_trade_date`
- `status`
- `status_text`
- `market_state`
- `topn_preview`
- `coverage_summary`
- `factor_gate_summary`
- `notes`

Public `status` values:

- `ready`
- `delayed`
- `partial`
- `unavailable`

## Status Rules

### Start Rule

If current time is later than `expected_start_at + 15 minutes` and no qualifying stage has entered `running` or `success`, mark:

- `intervention.needs_intervention = true`
- `intervention.severity = "critical"`
- `intervention.reason_code = "not_started"`

### Deadline Rule

If current time is later than `expected_done_by` and the workflow is not complete:

- mark `pipeline.overall_status = "delayed"`;
- if heartbeat is still fresh, severity stays `warning`;
- if heartbeat is stale or a required stage failed, severity escalates to `critical`.

### Stall Rule

If the most recent heartbeat or stage update is older than the configured threshold, mark:

- `health.stalled = true`
- `intervention.needs_intervention = true`
- `intervention.reason_code = "stalled"`

### Readiness Rule

Internal readiness is based on whether the latest ready trade date and required stage statuses show the daily dataset is usable. This must distinguish:

- workflow execution trouble that still leaves yesterday's data usable;
- workflow trouble that blocks today's dashboard and public release.

### Public Release Rule

The public page never reads raw task failure detail. It reads only publishable output:

- `ready` when the latest ready trade date matches the intended visible date and public summary inputs are present;
- `delayed` when the system is still showing the previous ready date but prior data remains valid;
- `partial` when a limited subset can be shown safely;
- `unavailable` when no trustworthy release snapshot exists.

## UI Structure

### Internal Ops Page

Top to bottom:

1. Hero status cards
   - workflow state
   - intervention state
   - latest ready trade date
   - current stage
2. Time commitment panel
   - planned vs actual start
   - planned vs actual finish
   - lateness indicator
3. Intervention panel
   - severity
   - reason
   - suggested action
4. Stage timeline panel
   - per-stage status, start time, elapsed time, summary
5. Snapshot preview panel
   - market state
   - TopN preview
   - coverage summary
   - factor gate summary

### Public Snapshot Page

Top to bottom:

1. Release state card
2. Latest ready trade date
3. Market state summary
4. TopN preview
5. Coverage summary

## Security And Access

- Internal page is deployed behind internal network or VPN plus login.
- Public page is read-only and hides task timing, failure details, source errors, and intervention guidance.
- Public data is derived from aggregated release-safe fields only.

## Testing Strategy

### Backend

- unit tests for `ops_snapshot.py` covering:
  - started on time;
  - missed start;
  - delayed but progressing;
  - stale heartbeat;
  - required stage failure;
  - public release fallback and degraded cases.
- API tests for the three new endpoints.

### Frontend

- client tests for the new fetch helpers;
- component tests for internal and public panels;
- app shell tests for internal view rendering and public route rendering.

## Rollout Strategy

### Phase 1

- backend aggregator
- three APIs
- internal operations page
- minimal public page

### Phase 2

- optional JSON/static snapshot cache for the public page
- history charts
- intervention trend summaries

## Risks

- Existing status sources may be incomplete for exact start and heartbeat inference.
- Some current readiness fields may describe availability but not operator actionability.
- Public summary may need explicit fallback wording when the visible date is older than today's target date.

## Decision

Proceed with one backend aggregation layer and two read-only page surfaces. Do not build a new standalone system. Reuse the current dashboard API and frontend structure, with backend-owned status rules and frontend-owned presentation only.
