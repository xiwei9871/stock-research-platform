# Dashboard Ops Snapshot Runbook

## Endpoints

- `GET /api/ops/snapshot`
- `GET /api/ops/stages`
- `GET /api/public/snapshot`

## Internal Page Questions

- Did the workflow start on time?
- Is intervention required?
- What is the current stage?
- What is the latest ready trade date?
- If `intervention.needs_intervention` is true, escalate the workflow and inspect the stage details before clearing the page.

## Public Page Rules

- Public page never exposes raw source failures.
- Public page reads only release-safe fields from the public snapshot.
- Public `coverage_summary` is an explicit allow-list. Only approved keys are
  published; today that means `coverage_summary.core` when present.
- Dashboard builds use the canonical AppShell frontend from
  `dashboard/index.html` and `dashboard/src/main.tsx`.
- Public-only frontend deployments are deprecated. Local intranet validation and
  external publication must use the same canonical bundle:

  ```bash
  cd /Users/xiwei/stock_research/dashboard
  pnpm build
  ```

- Do not reintroduce `dashboard/public-snapshot.html`,
  `dashboard/src/public-main.tsx`, `PublicSnapshotPage`, or a second frontend.
  See `docs/canonical-frontend.md`.
