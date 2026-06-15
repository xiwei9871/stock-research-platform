# v0.1 Local EOD Research Baseline Smoke Matrix

This matrix defines the release smoke checks for
`v0.1-local-eod-research-baseline`. It is intentionally focused on the local
EOD research loop and excludes real-time trading, broker connectivity,
production risk, and multi-tenant SaaS concerns.

## Scope

Baseline path:

1. EOD pipeline writes `data_run_manifest`, `run_manifest.json`, and
   `run_summary.json`.
2. Readiness v2 reports `OK`, `PARTIAL`, or `BLOCKED`.
3. Review Queue exposes candidate lineage.
4. Evidence Digest exposes section-level evidence status.
5. Review and Evidence snapshots are generated and queryable.
6. Operator decisions link to snapshots when available.
7. Stock Workspace provides a minimal local decision UI.

Out of scope:

- New strategies, factors, or data sources.
- Automatic trading, execution, orders, broker integration, position sizing, or
  live risk management.
- HomeCockpit redesign, Strategy Command Center, Backtest Lab expansion, and
  vectorized backtest feature work.

## Backend Smoke

| Check | Command | Expected Result |
| --- | --- | --- |
| Schema import | `PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python - <<'PY'\nfrom stock_research import schema\nprint('schema-ok')\nPY` | Imports without error. |
| Daily pipeline help | `PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli run-stock-daily-data-pipeline --help` | Command is registered. |
| Daily pipeline sample run | `PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli run-stock-daily-data-pipeline --trade-date YYYY-MM-DD --output-dir outputs/research/stock_daily_data_pipeline/YYYY-MM-DD --no-feishu` | Writes `run_summary.json` and `run_manifest.json`. |
| Snapshot CLI help | `PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli snapshot-review-evidence --help` | Command is registered. |
| Snapshot rerun | `PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli snapshot-review-evidence --run-id eod-YYYY-MM-DD-local --trade-date YYYY-MM-DD --output-dir outputs/research/stock_daily_data_pipeline/YYYY-MM-DD --limit 30` | Writes or updates review/evidence snapshots idempotently. |
| Readiness API | `curl -s http://127.0.0.1:8765/api/platform/readiness \| jq .` | Returns `status`, `run_id`, `latest_trade_date`, `tiers`, and `modules`. |
| Review Queue API | `curl -s 'http://127.0.0.1:8765/api/review-queue?limit=5' \| jq .` | Items include lineage, digest key, and evidence status when candidates exist. |
| Evidence Digest API | `curl -s 'http://127.0.0.1:8765/api/evidence-digest?asset_id=000001.SZ' \| jq .` | Returns section statuses and partial/missing evidence warnings. |
| Snapshot list APIs | `curl -s 'http://127.0.0.1:8765/api/review-queue/snapshots?run_id=eod-YYYY-MM-DD-local&limit=5' \| jq .` | Returns machine-readable snapshot rows or a clear empty result. |
| Operator decision POST | See `docs/dashboard-local-runbook.md`. | Decision writes without creating any execution instruction. |
| Decision readback | `curl -s 'http://127.0.0.1:8765/api/assets/000001.SZ/decisions?limit=5' \| jq .` | Decision includes snapshot linkage status and warnings. |

## Frontend Smoke

| Check | Command | Expected Result |
| --- | --- | --- |
| Dashboard build | `cd dashboard && pnpm build` | TypeScript and Vite build complete. |
| Client tests | `cd dashboard && pnpm exec vitest run --exclude "**/*.spec.ts" tests/client.test.ts` | API client tests pass. |
| Operator decision panel | `cd dashboard && pnpm exec vitest run --exclude "**/*.spec.ts" tests/operator-decision-panel.test.tsx` | Panel renders allowed research actions and handles linked/missing responses. |
| Stock Workspace | `cd dashboard && pnpm exec vitest run --exclude "**/*.spec.ts" tests/stock-workspace.test.tsx` | Workspace can render Evidence Digest and decision panel. |
| Review Queue Workspace | `cd dashboard && pnpm exec vitest run --exclude "**/*.spec.ts" tests/review-queue-workspace.test.tsx` | Review Queue remains compatible with lineage fields. |
| Playwright platform flow | `cd dashboard && pnpm exec playwright test tests/platform-full-flow.spec.ts` | Optional for release only when local API/frontend fixtures are stable. |

## Data Smoke

| Check | Expected Result |
| --- | --- |
| Manifest has run id | `ops.data_run_manifest` rows include `run_id`, `module`, `tier`, and `status`. |
| Summary has status | `run_summary.json` includes `status`, tier statuses, warnings, errors, and readiness status. |
| Manifest has snapshots | `run_manifest.json` includes `review_evidence_snapshots` as a Tier 2 module when the post-step runs. |
| Readiness is explicit | `/api/platform/readiness` returns one of `OK`, `PARTIAL`, or `BLOCKED`. |
| Snapshot counts exist | `run_summary.json` includes review item and evidence digest snapshot counts. |
| Decision linkage exists | Decision read model returns `snapshot_linkage_status`, snapshot ids, payload hashes, and warnings. |

## Failure Smoke

| Scenario | Expected Result |
| --- | --- |
| Tier 2 module fails | Readiness is `PARTIAL` when Tier 1 is otherwise usable. |
| Snapshot missing during decision write | POST succeeds, response returns `snapshot_linkage_status: missing` and warnings. |
| News or reports missing | Evidence Digest is `PARTIAL`, not a frontend crash. |
| Tier 1 missing or stale | Readiness is `BLOCKED`; Review Queue / score / TopN gaps appear in errors or next actions. |

## Focused Release Test Suite

Backend:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_data_run_manifest.py \
  tests/test_daily_data_pipeline.py \
  tests/test_dashboard_readiness.py \
  tests/test_dashboard_review_queue.py \
  tests/test_dashboard_evidence_digest.py \
  tests/test_review_evidence_snapshots.py \
  tests/test_operator_decision_snapshot_linkage.py \
  tests/test_operator_decision_write_service.py \
  tests/test_dashboard_decisions.py \
  tests/test_dashboard_app.py -q
```

Frontend:

```bash
cd dashboard && pnpm exec vitest run --exclude "**/*.spec.ts" \
  tests/client.test.ts \
  tests/operator-decision-panel.test.tsx \
  tests/stock-workspace.test.tsx \
  tests/review-queue-workspace.test.tsx
```

Build:

```bash
cd dashboard && pnpm build
```

## Tag Checklist

- Baseline docs and code are committed.
- Non-baseline dirty work is classified and isolated from the release commit.
- Schema imports and local database initialization path are known.
- EOD command and snapshot rerun command are documented.
- Readiness API responds with v2 shape.
- Dashboard builds.
- Operator Decision UI can submit a local research action.
- Snapshot linkage can be read back from the decision API.
- Smoke matrix and release note are present.
- Tag points at the release baseline commit, not at uncommitted work.
