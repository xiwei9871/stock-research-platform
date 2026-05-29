# P6 Dashboard Workbench Scope And Execution Plan

Date: 2026-05-30

## Status

P6 scope is adjusted and frozen around **Dashboard Workbench Integration
Hardening**.

P6 will use the existing `dashboard-workbench` branch as the implementation
baseline, but it should not be merged directly without hardening.

Current dashboard branch state:

- Branch: `dashboard-workbench`
- Worktree: `.worktrees/dashboard-workbench`
- Latest reviewed commit: `3938cae docs: add dashboard workbench runbook`
- Runbook: `.worktrees/dashboard-workbench/docs/dashboard-workbench-runbook.md`

## Decision

Adopt the dashboard workbench as the P6 baseline.

Do not restart the dashboard design from scratch. The branch already implements
the correct product direction:

- read-only research workbench
- React + Vite frontend
- Lightweight Charts chart surface
- FastAPI read-only backend
- TopN, score, watchlist, report, daily-bar, and minute-bar views
- browser smoke coverage

Do not merge it as-is. Before merge, P6 must harden integration boundaries,
dependency metadata, CLI conflicts, and review-only semantics.

## Product Positioning

P6 is a **research workbench**, not a trading terminal.

The TradingView-like experience means:

- chart-centered visual review
- selected asset context
- TopN and watchlist navigation
- score and signal inspection
- report link navigation

It does not mean:

- connecting to TradingView external services
- using TradingView private Charting Library
- cloning Pine Script
- placing orders
- connecting brokers
- showing an order ticket
- promising real-time market data

The current chart direction should remain based on `lightweight-charts` unless a
separate design explicitly approves a heavier charting dependency.

## Architecture

P6 keeps a thin dashboard layer on top of existing stock research outputs.

Backend:

- `src/stock_research/dashboard/`
- FastAPI app with read-only endpoints.
- Reads existing stores and artifacts only.
- Does not mutate factor, watchlist, report, scheduler, notification, or trading
  data.

Frontend:

- `dashboard/`
- React + Vite.
- Lightweight Charts for K-line and volume display.
- Reads dashboard API DTOs only.
- Does not write platform state.

Integration:

- `stock-research dashboard-api` is the intended local operator entrypoint.
- CLI integration must be merged carefully because main currently has unrelated
  Alpha191 changes in `src/stock_research/cli.py`.
- Generated frontend artifacts must stay out of git:
  - `dashboard/node_modules/`
  - `dashboard/dist/`
  - `dashboard/test-results/`
  - `dashboard/playwright-report/`

## P6 In Scope

### P6-0 Baseline Review

Goal: treat `dashboard-workbench` as a candidate P6 branch and review it against
mainline P3/P4/P5 boundaries.

Deliver:

- Confirm branch status is clean.
- Record changed files and generated-artifact policy.
- Confirm runbook exists and matches actual commands.
- Confirm the dashboard remains read-only.

Acceptance:

- No generated frontend or Python cache artifacts are tracked.
- Dashboard branch can be reviewed without touching main dirty Alpha191 files.

### P6-1 Backend Read-Only API Hardening

Goal: keep the dashboard backend narrow and read-only.

Deliver:

- Validate dashboard API routes only read from:
  - `market_daily_bar`
  - `market.stock_minute_bar`
  - `factor.stock_score_daily`
  - `watchlist.watchlist_daily_signal`
  - local `reports/` artifacts
- Keep DTOs explicit and JSON-safe.
- Ensure API tests cover missing assets, empty datasets, and shape stability.
- Check that FastAPI dependencies are declared correctly.

Known item to verify:

- `pyproject.toml` on the dashboard branch currently shows `httpx2` under dev
  dependencies. This looks like a typo and must be resolved before merge.

Acceptance:

- Backend dashboard tests pass.
- No write path is introduced.
- Dependency metadata installs cleanly.

### P6-2 Frontend Workbench Hardening

Goal: keep the UI as an operator research surface rather than a trading terminal.

Deliver:

- Preserve the current three-zone workbench:
  - navigation/sidebar for TopN and watchlist
  - central chart workspace
  - right inspector for score, signals, and reports
- Keep chart integration through a local chart adapter around Lightweight Charts.
- Add or verify empty/loading/error states.
- Ensure text and panels fit without overlap at target desktop and browser-smoke
  viewports.

Acceptance:

- Vitest passes.
- `pnpm build` passes.
- Playwright smoke passes.
- No order ticket, broker widget, or trading instruction UI is introduced.

### P6-3 P4/P5 Operational Context

Goal: make the dashboard compatible with P4/P5 operations without expanding P6
into notification infrastructure.

Deliver:

- Scope the dashboard as a consumer of scheduler/notification status, not as the
  owner of scheduler execution.
- P6 may display P4/P5 artifact status if the data is already available.
- P6 must not enable, install, or send notifications.

Acceptance:

- Dashboard can link to or display existing P4/P5 outputs only when read-only.
- Notification live-send remains outside the dashboard.

### P6-4 Mainline Rebase And CLI Integration

Goal: integrate the dashboard branch onto the P5 mainline without mixing unrelated
Alpha191 work.

Deliver:

- Rebase or merge `dashboard-workbench` onto current P5 mainline.
- Resolve `src/stock_research/cli.py` intentionally.
- Keep dashboard CLI addition minimal:
  - `stock-research dashboard-api --host 127.0.0.1 --port 8765`
- Do not delete or rewrite Alpha191 work unless explicitly requested.

Acceptance:

- CLI parser tests cover `dashboard-api`.
- Existing P4/P5 commands still parse.
- Alpha191 files remain either separately committed by their owner or clearly
  outside the dashboard merge.

### P6-5 Verification And Completion Review

Goal: prove the integrated dashboard branch is reviewable before merge.

Deliver:

- Backend dashboard tests.
- Frontend unit tests.
- Frontend build.
- Browser smoke test.
- Python regression suite, with Alpha191 test exclusion only if that other line is
  still intentionally unmerged.
- P6 completion review document.

Acceptance:

- Verification commands and results are recorded in the P6 completion review.
- Any excluded Alpha191 test is explicitly named.
- Merge decision is based on current evidence, not prior branch claims.

## Out Of Scope For P6

- Broker integration.
- Order placement.
- Trading account, cash, order, execution, or broker ledger tables.
- TradingView external service integration.
- TradingView private Charting Library.
- Pine Script compatibility.
- Alert rule authoring.
- Live market-data guarantees.
- Scheduler installation.
- Notification live-send enablement.
- Rewriting factor, watchlist, scoring, report, P3, P4, or P5 pipelines.

## Execution Order

1. P6-0: document this adjusted scope and commit it on main.
2. P6-1: review the dashboard branch diff and fix integration blockers on
   `dashboard-workbench`.
3. P6-2: run dashboard branch verification:
   - backend dashboard tests
   - frontend unit tests
   - frontend build
   - Playwright smoke
4. P6-3: rebase/merge dashboard branch onto the latest P5 mainline.
5. P6-4: resolve CLI integration and dependency metadata.
6. P6-5: run integrated verification.
7. P6 review: write P6 completion review and decide merge readiness.

## Merge Gate

The dashboard branch is merge-ready only when:

- `dashboard-workbench` is rebased or merged onto the latest P5 mainline.
- `pyproject.toml` has no invalid dependency typo.
- `src/stock_research/cli.py` conflict is resolved deliberately.
- Generated frontend artifacts are ignored and untracked.
- Backend dashboard tests pass.
- Frontend unit tests pass.
- Frontend build passes.
- Playwright smoke passes.
- Python regression passes, or the only exclusion is the explicitly separate
  Alpha191 pilot test.
- P6 completion review records all verification evidence.

## Safety Rules

- The dashboard is read-only.
- The dashboard must not create trading instructions.
- The dashboard must not place orders.
- The dashboard must not connect to brokers.
- The dashboard must not store secrets, webhook URLs, tokens, or broker account
  data.
- Chart interactions may filter and inspect data only.
- Any future write workflow requires a separate phase and safety design.

## Recommendation

Proceed with P6 by hardening and integrating `dashboard-workbench`.

Do not restart the dashboard from scratch, and do not merge the branch blindly.
The branch is the right implementation baseline, but P6 completion depends on
mainline integration, dependency cleanup, CLI conflict handling, and fresh
verification.
