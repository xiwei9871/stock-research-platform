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
- Normal dashboard builds use `dashboard/index.html` with
  `dashboard/src/main.tsx`. Those builds keep `/public` route support for local
  or shared deployments.
- Public-only deployments must build with:

  ```bash
  cd /Users/xiwei/stock_research/dashboard
  VITE_PUBLIC_SNAPSHOT_ONLY=true pnpm build
  ```

- That mode switches Vite to `dashboard/public.html`, which bootstraps
  `dashboard/src/public-main.tsx`. The resulting artifact imports only
  `PublicSnapshotPage` and shared styles, so it does not rely on a runtime
  branch inside a bundle that also imports `App`.
