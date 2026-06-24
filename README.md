# Stock Research Platform

This repository contains the downstream research platform for an AI-assisted
stock monitoring and stock-selection workflow.

The platform is complete through **P19 Final Platform Closure**. It supports
manual research operations, read-only dashboard review, operator decision
journaling, outcome analytics, offline experiment review, and a review-only
shadow lifecycle from watchlist candidates through P18 follow-up resolution.

This is **not** an automated trading system. It does not provide broker
integration, order execution, account state, cash mutation, position mutation,
or automatic production watchlist promotion.

## Current Release Status

- Branch: `factor-scoring-daily-pipeline`
- Final platform closure: `docs/quant_system/69_p19_final_platform_closure_completion.md`
- Phase index: `docs/quant_system/65_p19_platform_phase_index.md`
- Release readiness audit: `docs/quant_system/66_p19_release_readiness_audit.md`
- Final smoke matrix: `docs/quant_system/67_p19_final_smoke_matrix.md`
- Final release runbook: `docs/quant_system/68_p19_final_release_runbook.md`

P0-P19 have been committed and pushed to the remote branch. Later strategy work
such as alpha191, mid-trend research, strong-winner research, stock-report
collection, and additional watchlist experiments should be handled as separate
scopes.

## Platform Map

| Layer | Phases | Status |
| --- | --- | --- |
| Data foundation and daily operations | P0-P5 | Complete for the current research platform foundation. |
| Dashboard workbench | P6 | Complete as a read-only review dashboard. |
| Operator decision loop | P7-P11 | Complete for manual decisions, outcomes, analytics, governance, and offline replay. |
| Shadow research lifecycle | P12-P18 | Complete as a review-only shadow lifecycle. |
| Final release readiness | P19 | Complete with phase index, audit, smoke matrix, runbook, and completion review. |

## Core Capabilities

- Point-in-time research data model with schemas for core, market, finance,
  factor, backtest, simulation, watchlist, reports, ops, and shadow review
  read models.
- Daily factor scoring pipeline and daily operational runbooks.
- Read-only dashboard workbench for charts, TopN review, watchlist review,
  report navigation, outcome review, experiment review, and shadow review.
- Operator decision journal and outcome review artifacts.
- Decision outcome analytics and experiment proposal/replay governance.
- Shadow watchlist candidates, shadow outcome tracking, shadow outcome
  analytics, shadow operational review, shadow review decisions, follow-up
  queue, and P18 follow-up resolution review.
- Final smoke matrix covering backend focused tests, dashboard unit tests,
  dashboard build, and browser smoke.

## Safety Boundaries

The platform is designed for research and manual review.

- Shadow rows are not production approvals.
- P18 resolution labels are review labels only.
- Dashboard panels are read-only.
- Production promotion requires a separately scoped future phase.
- No broker, order, account, cash, position, fill, or execution state is managed
  by this platform foundation.
- Nothing in this repository is investment advice or an instruction to trade.

## Common Commands

Run the daily research script:

```bash
/Users/xiwei/stock_research/scripts/run_daily_research.sh
```

## Ops Snapshot Pages

Internal ops status:

```bash
curl http://127.0.0.1:8765/api/ops/snapshot
curl http://127.0.0.1:8765/api/ops/stages
```

Public snapshot:

```bash
curl http://127.0.0.1:8765/api/public/snapshot
```

Start the dashboard API:

```bash
stock-research dashboard-api --host 127.0.0.1 --port 8765
```

Build a P17 shadow follow-up queue:

```bash
stock-research p17-shadow-follow-up-queue \
  --p16-decisions-json outputs/p16/operator_shadow_review_decisions_2026-08-29.json \
  --run-id p17-shadow-follow-up-queue-2026-08-29 \
  --follow-up-date 2026-08-29 \
  --operator-id operator \
  --output-dir outputs/p17
```

Build a P18 follow-up resolution review:

```bash
stock-research p18-shadow-follow-up-resolution \
  --p17-follow-up-json outputs/p17/operator_shadow_follow_up_queue_2026-08-29.json \
  --run-id p18-shadow-follow-up-resolution-2026-08-29 \
  --resolution-date 2026-08-29 \
  --operator-id operator \
  --output-dir outputs/p18
```

Import P18 read-model rows:

```bash
stock-research p18-import-shadow-follow-up-resolution \
  --path outputs/p18 \
  --service stock_research
```

## Final Smoke

Run from the repository root:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_operator_shadow_follow_up_resolution.py \
  tests/test_operator_shadow_follow_up_resolution_read_model.py \
  tests/test_p18_shadow_follow_up_resolution_smoke.py \
  tests/test_p17_shadow_follow_up_queue_smoke.py \
  tests/test_schema.py \
  tests/test_factor_cli.py \
  tests/test_dashboard_shadow_follow_up_resolution.py \
  tests/test_dashboard_app.py \
  -k 'shadow_follow_up_resolution or p18_shadow_follow_up_resolution or p18_import_shadow_follow_up_resolution or p17_shadow_follow_up_queue or dashboard' \
  -q
```

Run from `dashboard/`:

```bash
pnpm test -- --run tests/client.test.ts tests/app-shell.test.tsx
pnpm build
pnpm exec playwright test tests/app-smoke.spec.ts
```

See `docs/quant_system/67_p19_final_smoke_matrix.md` for the full final smoke
matrix and expected evidence.

## Documentation Entry Points

| Topic | Document |
| --- | --- |
| Final phase index | `docs/quant_system/65_p19_platform_phase_index.md` |
| Release readiness audit | `docs/quant_system/66_p19_release_readiness_audit.md` |
| Final smoke matrix | `docs/quant_system/67_p19_final_smoke_matrix.md` |
| Final release runbook | `docs/quant_system/68_p19_final_release_runbook.md` |
| Final platform completion | `docs/quant_system/69_p19_final_platform_closure_completion.md` |
| Dashboard workbench | `docs/dashboard-workbench-runbook.md` |
| Dashboard ops snapshot runbook | `docs/dashboard-ops-snapshot-runbook.md` |
| Daily factor pipeline | `docs/daily-factor-pipeline-runbook.md` |
| P2 daily runbook and smoke report | `docs/quant_system/17_p2_daily_runbook_and_smoke_report.md` |
| P4 scheduler runbook | `docs/quant_system/21_p4_scheduler_runbook.md` |
| P17 follow-up queue runbook | `docs/quant_system/59_p17_shadow_decision_follow_up_queue_runbook.md` |
| P18 resolution review runbook | `docs/quant_system/62_p18_shadow_follow_up_resolution_review_runbook.md` |

## Data Principles

The database is a point-in-time stock research database. Values that change
over time must be stored with history, including ST status, suspension status,
industry membership, index or sector membership, share capital, and corporate
actions.

Financial statements and indicators must always carry both:

- `report_period`: the accounting period, such as `2025-12-31`
- `announcement_date`: the date the data became available to the market

Backtests and factor generation must only use finance rows where
`announcement_date <= trade_date`. Using a `report_period` before its
announcement date is a future-function bug and invalidates research results.

## Backtests

The repository includes research validation backtests such as:

```bash
stock-research backtest-top20 \
  --start-date 2024-05-01 \
  --end-date 2026-05-07 \
  --holding-days 3,5,7,10 \
  --top-n 20
```

```bash
stock-research portfolio-backtest \
  --start-date 2026-04-01 \
  --end-date 2026-05-07 \
  --initial-cash 500000 \
  --top-ks 5,10 \
  --holding-days 5,10,15,20,30
```

Backtest outputs are research validation artifacts. They do not provide trading
instructions, position instructions, order instructions, or investment advice.
