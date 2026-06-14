# Platform Closure And Operational Readiness Phase 12 Design

## Goal

Phase 12 closes the local research dashboard build-out by making the existing Phase 1-11 workspaces reliable as a daily EOD research cockpit.

The platform should let a user open localhost, start from Home, review the EOD candidate queue, inspect a stock's evidence, and move through News, Research Reports, and Market Monitor without losing context or seeing unclear empty/error states.

This phase is a closure and readiness phase. It should not expand the product into workflow state, realtime data, AI analysis, or trading.

The user should be able to answer:

- What data date and operating mode is this dashboard using?
- Which daily workspace should I open first?
- Can I move from Review Queue to Stock Detail and source workspaces without losing date or asset context?
- If a data source is empty or unavailable, what is missing and what can I still use?
- How do I run and verify the local dashboard again tomorrow?

## Scope

Phase 12 includes:

- Add a lightweight platform readiness contract that summarizes local operating mode, key workspace availability, EOD assumptions, and known warnings.
- Surface readiness and freshness clearly in Home so the user can tell the platform is EOD and local-data backed.
- Tighten the primary daily path:
  - Home
  - Review Queue
  - Stock Workspace
  - News
  - Research Reports
  - Market Monitor
- Improve empty, loading, and error states where the primary path currently feels ambiguous.
- Clarify workspace naming and copy for:
  - `News`: public news flow.
  - `Research Reports`: external broker/institution reports.
  - `Generated Reports`: local generated artifacts.
  - `Review Queue`: EOD candidate action inbox.
- Add a short local runbook for starting localhost, expected EOD data behavior, and verification commands.
- Add focused backend, frontend, and e2e coverage for readiness and the full daily path.

Phase 12 excludes:

- Persistent user review state such as reviewed, snoozed, assigned user, notes, or review history.
- Realtime fetching, polling, websocket behavior, or intraday guarantees.
- AI summaries, semantic ranking, or new analysis models.
- Trading, order routing, broker integration, or portfolio execution.
- Large UI framework migration or redesign.
- Cleanup of unrelated dirty worktree changes.

## Product Behavior

### Home Readiness Strip

Home should show a compact readiness strip near the top of the cockpit.

It should communicate:

- operating mode: `EOD local`;
- latest market date when known;
- review queue status;
- news status;
- research report status;
- generated report status;
- warning count.

The strip should use concise labels and honest status text. It should not imply realtime coverage.

Suggested states:

- `Ready`: required local read models are usable.
- `Partial`: at least one optional source is unavailable, but the dashboard can still be used.
- `Missing data`: core EOD data needed for the daily flow is unavailable.

### Daily Path

The primary workflow is:

1. Open Home and inspect readiness.
2. Open Review Queue.
3. Select a candidate and open Stock Workspace.
4. Review Evidence Digest and source-backed facts.
5. Open News, Research Reports, or Market Monitor from the stock context.
6. Return to Stock Workspace with the original asset and trade date preserved.

Phase 12 should verify this as one local smoke path. The path should be robust when individual sources are thin or empty.

### Empty And Error States

Empty states should explain what is missing and preserve useful controls.

Examples:

- Review Queue empty: show selected trade date, score version, and that no candidates were available.
- News empty: show whether this is an empty source response, quality filtering, or collector/source issue when known.
- Research Reports empty: show the active query/date filters.
- Market Monitor unavailable: keep the selected EOD date visible and show warnings.
- Stock Workspace digest unavailable: keep asset profile, related news, and reports visible when available.

Errors should be local to the affected panel where possible. A failed optional source should not blank the whole cockpit.

## Recommended Approach

Add one small backend readiness read model and use existing frontend workspaces for the rest.

This is the recommended approach because:

- Phase 7-11 already built the core EOD data and navigation surfaces.
- A readiness contract gives Home a stable way to explain data availability without duplicating source checks in React.
- The closure phase should reduce ambiguity and regression risk, not introduce new durable workflow state.
- Focused tests and a runbook make the platform easier to operate after this build sequence ends.

## Alternatives Considered

### Persistent Review Workflow

Adding reviewed/snooze/notes would make Review Queue more operational, but it creates schema, migration, conflict, and product semantics. It should be a future phase after the read-only daily workflow is trusted.

### Real-Time Monitor

Realtime fetching would make Monitor and News more dynamic, but it increases network and server pressure and changes the platform promise. The agreed boundary is EOD first.

### AI Research Assistant

Generated summaries may be useful later, but they add cost, latency, hallucination risk, prompt/version management, and source attribution concerns. Phase 12 should close the deterministic local platform.

## Backend Architecture

Add or extend a backend module for readiness:

- `src/stock_research/dashboard/readiness.py`

Expose:

- `GET /api/platform/readiness`

Suggested response:

```json
{
  "mode": "eod_local",
  "status": "partial",
  "as_of": "2026-06-15T00:00:00+08:00",
  "latest_market_date": "2026-06-12",
  "checks": [
    {
      "key": "review_queue",
      "label": "Review Queue",
      "status": "ready",
      "detail": "Queue available for 2026-06-12"
    },
    {
      "key": "news",
      "label": "News",
      "status": "partial",
      "detail": "Public news source available with quality filtering"
    }
  ],
  "warnings": []
}
```

Field rules:

- `mode` is `eod_local` for Phase 12.
- `status` is one of `ready`, `partial`, or `missing_data`.
- `checks[].status` is one of `ready`, `partial`, `missing_data`, or `unknown`.
- Warnings should be plain operational messages, not stack traces.

The readiness endpoint may compose existing read helpers, but it should stay lightweight and bounded. It must not trigger expensive backfills or source ingestion.

## Frontend Architecture

Expected frontend edits are limited to:

- `dashboard/src/api/types.ts`
- `dashboard/src/api/client.ts`
- `dashboard/src/components/HomeCockpit.tsx`
- `dashboard/src/components/AppShell.tsx`
- `dashboard/src/components/ReviewQueueWorkspace.tsx`
- `dashboard/src/components/StockWorkspace.tsx`
- related tests and e2e fixtures.

Home should call readiness once on mount and render it independently from existing platform summary, market monitor, news, and evidence digest calls.

Readiness failure should degrade to a local warning, not block Home.

## Runbook

Add a short document:

- `docs/dashboard-local-runbook.md`

It should include:

- backend/frontend startup commands;
- expected localhost URLs;
- EOD data assumption;
- useful verification commands;
- known source limitations;
- what to check when Review Queue, News, Research Reports, or Market Monitor is empty.

## Testing

Backend tests should cover:

- readiness endpoint returns `eod_local` mode;
- status aggregation chooses `ready`, `partial`, and `missing_data` deterministically;
- source failures become warnings instead of unhandled errors.

Frontend tests should cover:

- Home renders the readiness strip;
- readiness failure shows a local warning while Home still renders;
- Review Queue action still opens Stock with the selected trade date;
- Stock source actions still preserve trade date through News and Research Reports.

E2E should cover:

- Home readiness visible;
- opening Review Queue from nav;
- opening a stock from Review Queue;
- opening at least one source workspace from Stock;
- returning without losing the original asset/date context.

Verification should include:

- backend focused tests;
- frontend focused tests;
- dashboard build;
- dashboard e2e.

## Completion Criteria

Phase 12 is complete when:

- `/api/platform/readiness` exists and returns deterministic local EOD status.
- Home displays readiness/freshness without blocking existing cockpit sections.
- Core daily path remains navigable and context-preserving.
- Ambiguous empty/error states on the primary path are improved.
- `docs/dashboard-local-runbook.md` documents localhost startup and EOD assumptions.
- Focused backend and frontend tests pass.
- Dashboard build passes.
- Mocked e2e path passes.
- Phase 12 commits are separated from unrelated dirty worktree changes.
