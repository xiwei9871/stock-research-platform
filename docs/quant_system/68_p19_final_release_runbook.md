# P19 Final Release Runbook

## Purpose

This is the final operating runbook for the completed stock research platform
foundation. It gives a safe order for daily research operation, review artifact
generation, read-model import, dashboard inspection, and failure handling.

This runbook does not authorize production trading.

## Operating Principles

- Treat the platform as a research and review system.
- Generate local artifacts before importing read-model rows.
- Import read models before relying on dashboard panels.
- Keep dashboard usage read-only.
- Treat all shadow and P18 resolution outputs as manual-review labels.
- Stop on failed smoke tests before making release or operational claims.

## Preflight

Run from the repository root:

```bash
git status --short
git log --oneline -5
```

Expected:

- You know which branch and commit are being operated.
- Any unrelated dirty changes are understood and protected before merge or
  release work.

Run the final focused smoke:

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

Expected:

- All selected tests pass.

## Schema And Read Models

Apply schema when deploying to a database that may not have the latest ops
tables:

```bash
stock-research apply-schema
```

P17/P18 read-model tables expected by the final shadow review loop:

- `ops.operator_shadow_follow_up_run`
- `ops.operator_shadow_follow_up_item`
- `ops.operator_shadow_follow_up_resolution_run`
- `ops.operator_shadow_follow_up_resolution_item`

If dashboard P17/P18 panels are empty, first check whether the relevant import
commands have run and whether the tables exist.

## Daily Foundation Operations

Use the existing phase runbooks for daily operation details:

- P2 daily runbook and smoke report:
  - `docs/quant_system/17_p2_daily_runbook_and_smoke_report.md`
- P4 scheduler runbook:
  - `docs/quant_system/21_p4_scheduler_runbook.md`
- P5 notification runbook:
  - `docs/quant_system/24_p5_notification_runbook.md`

P19 does not change those commands. It only makes their place in the final
platform explicit.

## Operator And Shadow Artifact Order

For the final review chain, preserve this order:

1. P7 operator decision journal.
2. P8 decision outcome review.
3. P9 decision outcome analytics.
4. P10 experiment governance review.
5. P11 offline experiment replay.
6. P12 shadow watchlist review.
7. P13 shadow outcome tracking.
8. P14 shadow outcome analytics.
9. P15 shadow analytics operational review.
10. P16 shadow review decisions.
11. P17 shadow follow-up queue.
12. P18 shadow follow-up resolution review.

Each phase reads prior artifacts and writes its own local artifacts and
independent read-model rows. Do not skip a phase unless you are intentionally
reviewing only a later artifact with known inputs.

## P17 Follow-Up Queue

Build P17 artifacts from P16 decisions:

```bash
stock-research p17-shadow-follow-up-queue \
  --p16-decisions-json outputs/p16/operator_shadow_review_decisions_2026-08-29.json \
  --run-id p17-shadow-follow-up-queue-2026-08-29 \
  --follow-up-date 2026-08-29 \
  --operator-id operator \
  --output-dir outputs/p17
```

Import P17 read model:

```bash
stock-research p17-import-shadow-follow-up-queue \
  --path outputs/p17 \
  --service stock_research
```

P17 records follow-up work. It does not approve production actions.

## P18 Resolution Review

Build P18 artifacts from P17 follow-up queue:

```bash
stock-research p18-shadow-follow-up-resolution \
  --p17-follow-up-json outputs/p17/operator_shadow_follow_up_queue_2026-08-29.json \
  --run-id p18-shadow-follow-up-resolution-2026-08-29 \
  --resolution-date 2026-08-29 \
  --operator-id operator \
  --output-dir outputs/p18
```

Import P18 read model:

```bash
stock-research p18-import-shadow-follow-up-resolution \
  --path outputs/p18 \
  --service stock_research
```

P18 labels follow-up resolution state. It does not mutate P17 rows and does not
create production approval.

## Dashboard Operation

Start the dashboard API:

```bash
stock-research dashboard-api --host 127.0.0.1 --port 8765
```

Dashboard review panels to inspect:

- Score and watchlist panels.
- Decision history.
- Outcome history.
- Outcome analytics.
- Experiment proposals and replay.
- Shadow watchlist.
- Shadow outcomes.
- Shadow outcome analytics.
- Shadow analytics review.
- Shadow review decisions.
- Shadow follow-up queue.
- Shadow follow-up resolution.

P17 endpoint:

```text
/api/shadow-follow-up-queue?start_date=2026-06-01&end_date=2026-08-31&limit=20
```

P18 endpoint:

```text
/api/shadow-follow-up-resolution?start_date=2026-06-01&end_date=2026-08-31&limit=20
```

Dashboard panels are inspection surfaces only. Do not infer production approval
from button absence or row status. Production promotion requires a separately
scoped future phase.

## Final Dashboard Smoke

Run from `dashboard/`:

```bash
pnpm test -- --run tests/client.test.ts tests/app-shell.test.tsx
pnpm build
pnpm exec playwright test tests/app-smoke.spec.ts
```

Expected:

- Vitest passes.
- Production build passes.
- Browser smoke passes on desktop and mobile.

## Failure Handling

| Failure | Response |
| --- | --- |
| Schema table missing | Run `stock-research apply-schema`, then rerun import. |
| P17/P18 dashboard panel empty | Check artifact exists, import command ran, date range matches, and table exists. |
| P18 artifact has zero items | Confirm P17 artifact has items and follow-up statuses are supported. |
| Focused pytest fails | Stop and fix before claiming release readiness. |
| Dashboard build fails | Stop and fix TypeScript or frontend integration before release. |
| Playwright smoke fails | Inspect panel visibility, API route mocks, and responsive overflow. |
| Dirty worktree includes unrelated files | Protect unrelated changes before merge/release work. |

## Final Safety Boundary

The completed foundation supports research review. It does not support:

- automated trading,
- broker execution,
- production order management,
- production watchlist promotion,
- treating shadow or P18 resolution rows as approval.

Those capabilities require new scope freeze, design, implementation plan,
tests, runbook, and completion review.
