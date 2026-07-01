# Canonical Frontend

## Definition

The canonical frontend is the single React SPA served from `dashboard/index.html`.

Its runtime entrypoint is:

`dashboard/src/main.tsx` -> `dashboard/src/App.tsx` -> `dashboard/src/components/AppShell.tsx`

This AppShell frontend is the only supported UI for both local intranet debugging and external publication. It includes the Home cockpit, Review Queue, Daily Review, Market Monitor, News, Research Reports, Stock Workspace, Watchlist, Factor Lab, Strategy Lab, and Generated Reports workspaces.

## Deployment Rule

Local intranet and external site deployments must serve the same canonical frontend bundle. Daily work should first validate `http://127.0.0.1:5174/`, then publish that same built artifact to `https://stock.manqiaotechnology.com/`.

## Explicitly Not Canonical

Do not reintroduce separate public snapshot pages, public dashboard entrypoints, or ops snapshot frontends such as:

- `public.html`
- `public-snapshot.html`
- `src/public-main.tsx`
- `PublicSnapshotPage`
- `OpsSnapshotPanel`
- `OpsStagesPanel`
- `Daily A-share Snapshot`

If a lightweight external view is needed later, it should be implemented as a workspace or route inside the canonical AppShell frontend, not as a second frontend.

## Guardrail

`dashboard/tests/canonical-frontend-entry.test.ts` protects this rule by failing when legacy public snapshot frontend entrypoints are present.
