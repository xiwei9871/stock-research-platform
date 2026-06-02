# P6 Completion Review

Date: 2026-05-30

## Status

P6 is ready for merge review.

Scope covered: **Dashboard Workbench Integration Hardening**.

P6 stayed inside the adjusted scope from:

- `docs/quant_system/26_p6_dashboard_workbench_scope_and_execution_plan.md`

## Branch State

Feature branch:

- `dashboard-workbench`

Worktree:

- `.worktrees/dashboard-workbench`

Mainline base:

- `factor-scoring-daily-pipeline`
- Rebased onto `c466dab docs: adjust p6 dashboard workbench plan`

Latest P6 branch head at review time:

- `85424a1 fix: harden dashboard worktree integration tests`

## Delivered Capabilities

### P6-0 Baseline Review

Review document:

- `docs/p6-dashboard-branch-review.md`

Decision:

- Keep `dashboard-workbench` as the P6 implementation baseline.
- Do not restart dashboard work from scratch.
- Do not treat the dashboard as a trading terminal.

### P6-1 Backend Read-Only API

Backend package:

- `src/stock_research/dashboard/`

Delivered read-only areas:

- dashboard schemas
- score read models
- bar read models
- watchlist read models
- report link index
- overview aggregation
- FastAPI app and local runner

Data sources:

- `market_daily_bar`
- `market.stock_minute_bar`
- `factor.stock_score_daily`
- `watchlist.watchlist_daily_signal`
- local `reports/` artifacts

CLI:

- `stock-research dashboard-api --host 127.0.0.1 --port 8765`

Boundary:

- No write path to factor, watchlist, report, scheduler, notification, broker,
  order, account, cash, or execution state.

### P6-2 Frontend Workbench

Frontend workspace:

- `dashboard/`

Delivered UI:

- React + Vite dashboard shell.
- Lightweight Charts K-line and volume chart.
- TopN list.
- Watchlist list.
- Score and signal inspector.
- Report panel.
- Loading states.
- Empty states.
- Desktop and mobile browser smoke coverage.

Boundary:

- No broker widget.
- No order ticket.
- No trading instruction UI.
- No TradingView external service dependency.

### P6-3 Mainline Rebase

Rebase command:

```bash
git rebase factor-scoring-daily-pipeline
```

Result:

```text
Successfully rebased and updated refs/heads/dashboard-workbench.
```

No manual conflict resolution was required.

### P6-4 CLI And Integration

Post-rebase CLI includes:

- `dashboard-api`
- P4 scheduler commands
- Alpha191 pilot and expanded validation commands

Integration fix:

- `tests/test_p5_notify_script.py` now uses `sys.executable` instead of
  `.venv/bin/python`.

Reason:

- The dashboard worktree does not contain a local `.venv`.
- The test must run with the active pytest interpreter.

## Delivered Review Documents

- `docs/dashboard-workbench-runbook.md`
- `docs/p6-dashboard-branch-review.md`
- `docs/p6-dashboard-frontend-review.md`
- `docs/p6-dashboard-mainline-integration-review.md`

## Acceptance Criteria Review

| Criterion | Status | Evidence |
| --- | --- | --- |
| Dashboard branch is rebased onto latest P5/P6 mainline | Pass | Rebased onto `c466dab`; rebase completed without conflict |
| `pyproject.toml` has no current install blocker | Pass | `pip install --dry-run -e ".[dashboard,dev]"` resolves |
| `src/stock_research/cli.py` conflict is resolved deliberately | Pass | `dashboard-api`, P4/P5, and Alpha191 commands coexist |
| Generated frontend artifacts are ignored and untracked | Pass | No tracked `dashboard/dist`, `dashboard/test-results`, `dashboard/playwright-report`, or `dashboard/node_modules` |
| Backend dashboard tests pass | Pass | `tests/test_dashboard_*.py` included in targeted and full runs |
| Frontend unit tests pass | Pass | `pnpm test`: `13 passed` |
| Frontend build passes | Pass | `pnpm build`: Vite build completed |
| Playwright smoke passes | Pass | `pnpm test:e2e`: `2 passed` |
| Python regression passes | Pass | `.venv/bin/pytest -q`: `1257 passed, 2 warnings` |
| Dashboard remains read-only | Pass | No broker/order/write path introduced |

## Verification Evidence

Dashboard backend and CLI targeted verification:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_*.py tests/test_factor_cli.py -q
```

Result:

```text
163 passed, 2 warnings
```

Frontend unit/build/e2e verification:

```bash
pnpm test && pnpm build && pnpm test:e2e
```

Result:

```text
Vitest: 13 passed
Vite build: built in 503ms
Playwright: 2 passed
```

Full Python regression:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest -q
```

Result:

```text
1257 passed, 2 warnings
```

The warnings are existing `py_mini_racer` deprecation warnings.

## Safety Review

- No broker adapter was added.
- No order placement was added.
- No account, cash, order, execution, or broker ledger table was added.
- No scheduler installation was added.
- No notification live-send enablement was added.
- No TradingView external service integration was added.
- No TradingView private Charting Library dependency was added.
- Dashboard interactions filter, inspect, and navigate existing read-only data.

## Known Non-P6 Main Worktree Files

The main worktree currently has unrelated uncommitted files that are not part of
this P6 branch:

- `src/stock_research/cli.py`
- `src/stock_research/strong_winner_miss_analysis.py`
- `tests/test_strong_winner_miss_analysis.py`

Do not merge P6 directly into that dirty worktree.

## Merge Decision

P6 is merge-ready from the `dashboard-workbench` branch perspective.

Recommended merge path:

1. Keep `dashboard-workbench` branch and worktree intact.
2. Merge into a clean mainline worktree, or first commit/stash the unrelated
   main-worktree strong-winner changes.
3. After merge, rerun:
   - `/Users/xiwei/stock_research/.venv/bin/pytest -q`
   - `cd dashboard && pnpm test && pnpm build && pnpm test:e2e`
4. Only then mark P6 as merged into mainline.
