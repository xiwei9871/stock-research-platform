# Dashboard Local Runbook

This runbook is for operating the local EOD dashboard on a developer or
operator machine. The dashboard is EOD-local, not real-time: it reads local
database rows and report artifacts that were already refreshed by the daily
pipeline. It should not be used as a live market monitor or as an order entry
surface.

## Environment Preparation

Use the project virtualenv and repository-local imports:

```bash
cd /Users/xiwei/stock_research/.worktrees/strategy-validation-visualization
export PYTHONPATH=src
/Users/xiwei/stock_research/.venv/bin/python --version
```

Install or refresh dashboard dependencies when `dashboard/package.json` changes:

```bash
cd dashboard
pnpm install
```

Initialize or upgrade the local database with the repository schema before a
fresh EOD run. Use the project command or test fixture already configured for
your local database; the v0.1 baseline expects the `ops.data_run_manifest`,
review/evidence snapshot, and operator decision tables declared by
`src/stock_research/schema.py`.

Required runtime assumptions:

- Local Python virtualenv exists at `/Users/xiwei/stock_research/.venv`.
- `PYTHONPATH=src` is set for module-style CLI commands.
- The local database configured by the project can be reached.
- Dashboard frontend dependencies are installed with `pnpm`.
- The workflow is EOD-local, not real-time.

## Local Startup

Start the API from the repository root with the project virtualenv:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/stock-research dashboard-api --host 127.0.0.1 --port 8765
```

If the virtualenv is already activated or the package is installed on PATH,
`stock-research dashboard-api --host 127.0.0.1 --port 8765` is equivalent.

Start the frontend in another shell:

```bash
cd dashboard
pnpm dev --host 127.0.0.1 --port 5174
```

Open the local dashboard:

```text
http://127.0.0.1:5174
```

Use localhost only for this workflow. The Vite frontend proxies dashboard API
calls to the local API, and the API reads the local configured research service
and local report artifacts.

## Data Refresh And Readiness

Refresh data before opening the dashboard. The v0.1 local EOD entrypoint is:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli run-stock-daily-data-pipeline \
  --trade-date YYYY-MM-DD \
  --output-dir outputs/research/stock_daily_data_pipeline/YYYY-MM-DD \
  --no-feishu
```

After the refresh, check platform readiness:

```bash
curl -s "http://127.0.0.1:8765/api/platform/readiness"
```

The readiness v2 payload reports:

- `status`: `OK`, `PARTIAL`, or `BLOCKED`.
- `run_id`: the latest EOD run identifier when available.
- `latest_trade_date`: the market date driving Review Queue, Evidence Digest,
  and snapshots.
- `tiers`: Tier 1 / Tier 2 / Tier 3 status summary from the manifest.
- `modules`: module-level status from `ops.data_run_manifest` or
  `run_summary.json`.
- `warnings`, `errors`, `missing_data`, and `partial_data`: actionable gaps for
  the daily review.
- `summary_path`: the machine-readable `run_summary.json` used by readiness,
  when available.

The readiness endpoint is lightweight and must not trigger backfills, scraping,
or real-time source ingestion.

## Daily Workflow

1. Run the EOD refresh and snapshot post-step, or confirm the EOD command
   completed both.
2. Start the local API and frontend.
3. Open Home at `http://127.0.0.1:5174` and inspect Platform Readiness.
4. Open Review Queue and review the EOD candidate list for the selected
   `latest_market_date`.
5. Open a candidate stock and review Evidence Digest, related News, Research
   Reports, and generated Reports.
6. Record a local operator decision such as `watch`, `note`, `follow_up`, or
   `skip`. The UI should show `Snapshot linked` or `Snapshot missing`.
7. Confirm the decision appears in Review / Outcomes or the asset decision API.
8. Use News and Reports to inspect source context, then return to the stock or
   Review Queue with the same date context.
9. Open EOD Monitor to compare the market snapshot, candidate pressure, and
   local EOD conditions for the same operating date.
10. Use Data Explorer, Factor Lab, Backtest Lab, and Strategy Validation only
   for deeper local review. They are supporting workspaces, not real-time
   decision automation.

## Troubleshooting

- API does not respond: confirm `/Users/xiwei/stock_research/.venv/bin/stock-research
  dashboard-api --host 127.0.0.1 --port 8765` is still running and that no
  other process owns port `8765`.
- Frontend does not load: run `cd dashboard && pnpm dev` and open
  `http://127.0.0.1:5174`.
- Readiness is `BLOCKED`: inspect Tier 1 modules in `/api/platform/readiness`,
  then open `run_summary.json` and `run_manifest.json` for the latest run.
- Readiness is `PARTIAL`: inspect Tier 2 / Tier 3 warnings. News, reports, LHB,
  generated reports, or snapshot failures should not block Tier 1 review, but
  they must be visible before manual review.
- Review Queue is empty: confirm Platform Summary has TopN preview data for the
  selected score version and market date.
- News is empty: distinguish a true empty source result from local collector,
  quality filter, or database issues. The readiness check reads
  `research.news_event_source`.
- Research Reports is empty: confirm the active filters/date window and that
  `research.stock_report_source` has imported rows.
- Generated Reports is empty: confirm local `reports/` artifacts exist for the
  `latest_market_date`.
- EOD Monitor looks stale: compare its selected trade date with
  `/api/platform/readiness` `latest_trade_date`; this dashboard does not
  continuously stream intraday updates.

## Acceptance Checks

Before handing the local dashboard to an operator:

- API starts on `127.0.0.1:8765`.
- Frontend opens on `http://127.0.0.1:5174`.
- `/api/platform/readiness` returns JSON with `status`, `run_id`, `tiers`,
  `modules`, and a meaningful `latest_trade_date`.
- Home shows Platform Readiness without blocking the rest of the dashboard.
- Review Queue opens and either shows candidates or a clear empty state for the
  selected EOD date.
- Evidence Digest shows section-level `available`, `partial`, `missing`, or
  `unavailable` state instead of crashing when auxiliary evidence is incomplete.
- Operator Decision Panel can submit a non-execution research action and show
  snapshot linkage status.
- News, Reports, Review Queue, and EOD Monitor are reachable from navigation.
- Stock detail preserves date and asset context when moving to News or Reports.
- The operator understands the dashboard is EOD-local rather than real-time.

## EOD Manifest Smoke

Run the local EOD pipeline with an explicit output directory:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli run-stock-daily-data-pipeline \
  --trade-date YYYY-MM-DD \
  --output-dir outputs/research/stock_daily_data_pipeline/YYYY-MM-DD \
  --no-feishu
```

Inspect:

- `run_summary.json`
- `run_manifest.json`
- `review_evidence_snapshots_summary.json`, when Review Queue candidates were
  available
- `http://127.0.0.1:8765/api/platform/readiness`

The EOD pipeline includes the Tier 2 `review_evidence_snapshots` post-step.
Snapshot failures should make readiness `PARTIAL`, not `BLOCKED`, when Tier 1
data and Review Queue are available.

To rerun only the snapshot post-step from existing Review Queue / Evidence
Digest read models:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli snapshot-review-evidence \
  --run-id eod-YYYY-MM-DD-local \
  --trade-date YYYY-MM-DD \
  --output-dir outputs/research/stock_daily_data_pipeline/YYYY-MM-DD \
  --limit 30
```

After importing an operator decision journal, check snapshot linkage through the
asset decision API:

```bash
curl -s "http://127.0.0.1:8765/api/assets/ASSET_ID/decisions?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&limit=5"
```

Decision rows should include `snapshot_linkage_status`. `linked` means the row
has Review Queue or Evidence Digest snapshot IDs. `missing` is allowed for
manual or historical decisions, but `snapshot_linkage_warnings` should explain
which snapshot lookup failed.

## Operator Decision Write API Smoke

Use the explicit write API for local manual research decisions. This records a
review item only; it does not create orders or execution instructions.

```bash
curl -s -X POST "http://127.0.0.1:8765/api/operator-decisions" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_id": "000001.SZ",
    "stock_code": "000001.SZ",
    "decision_date": "YYYY-MM-DD",
    "operator_action": "watch",
    "decision_status": "open",
    "operator_note": "manual review note",
    "run_id": "eod-YYYY-MM-DD-local",
    "digest_key": "YYYY-MM-DD:manual_v1:000001.SZ",
    "source_context": {
      "entry": "review_queue",
      "note_source": "dashboard"
    }
  }' | jq .
```

Then read it back:

```bash
curl -s "http://127.0.0.1:8765/api/assets/000001.SZ/decisions?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&limit=5" | jq .
```

Expected fields:

- `operator_action` is stored in `source_context`.
- `decision_label` remains one of the existing read-model labels.
- `snapshot_linkage_status` is `linked` when matching snapshots exist.
- `snapshot_linkage_status` is `missing` with warnings when the decision is
  manual, historical, or written before snapshot generation.

## API Smoke

With the API running on `127.0.0.1:8765`, check the v0.1 baseline path:

```bash
curl -s "http://127.0.0.1:8765/api/platform/readiness" | jq .
curl -s "http://127.0.0.1:8765/api/review-queue?limit=5" | jq .
curl -s "http://127.0.0.1:8765/api/evidence-digest?asset_id=000001.SZ" | jq .
curl -s "http://127.0.0.1:8765/api/review-queue/snapshots?run_id=eod-YYYY-MM-DD-local&limit=5" | jq .
curl -s "http://127.0.0.1:8765/api/evidence-digest/snapshots?run_id=eod-YYYY-MM-DD-local&limit=5" | jq .
```

Then run the operator decision POST smoke above and read back the asset
decisions. A missing snapshot linkage is a warning, not a failed manual
decision.

## Operator Decision UI Smoke

Use the dashboard UI for the same local manual decision workflow:

1. Open `http://127.0.0.1:5174`.
2. Go to Review Queue and open a candidate with `Review Stock`, or go directly
   to Stock Workspace.
3. Wait for Evidence Digest to load.
4. In `Operator Decision`, choose `watch`, `note`, `follow_up`, or another
   non-execution research action.
5. Enter a short note and save.
6. Confirm the panel shows `Decision saved`, the event id, and either
   `Snapshot linked` or `Snapshot missing`.
7. If the snapshot is missing, read the warning. This is allowed for manual or
   historical decisions.
8. Confirm Review / Outcomes refreshes with the newly persisted decision.
