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
- Check `intervention.needs_intervention` when deciding whether escalation is needed.

## Public Page Rules

- Public page never exposes raw source failures.
- Public page reads only release-safe fields from the public snapshot.
