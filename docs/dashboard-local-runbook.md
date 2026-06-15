# Dashboard Local Runbook

This runbook is for operating the local EOD dashboard on a developer or
operator machine. The dashboard is EOD-local, not real-time: it reads local
database rows and report artifacts that were already refreshed by the daily
pipeline. It should not be used as a live market monitor or as an order entry
surface.

## Local Startup

Start the API from the repository root with the project virtualenv:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research dashboard-api --host 127.0.0.1 --port 8765
```

If the virtualenv is already activated or the package is installed on PATH,
`stock-research dashboard-api --host 127.0.0.1 --port 8765` is equivalent.

Start the frontend in another shell:

```bash
cd dashboard
pnpm dev
```

Open the local dashboard:

```text
http://127.0.0.1:5174
```

Use localhost only for this workflow. The Vite frontend proxies dashboard API
calls to the local API, and the API reads the local configured research service
and local report artifacts.

## Data Refresh And Readiness

Refresh data before opening the dashboard. The normal local EOD entrypoint is:

```bash
/Users/xiwei/stock_research/scripts/run_daily_research.sh
```

After the refresh, check platform readiness:

```bash
curl -s "http://127.0.0.1:8765/api/platform/readiness"
```

The readiness payload should report `mode` as `eod_local`. Review:

- `status`: overall local readiness, usually `ready`, `partial`, or
  `missing_data`.
- `latest_market_date`: the market date driving Home, Review Queue, and EOD
  Monitor context.
- `checks`: availability for Platform Summary, Review Queue, News, Research
  Reports, and Generated Reports.
- `warnings`: missing or partial local data to resolve before daily review.

The readiness endpoint is lightweight and must not trigger backfills, scraping,
or real-time source ingestion.

## Daily Workflow

1. Run the EOD refresh and start the local API and frontend.
2. Open Home at `http://127.0.0.1:5174` and inspect Platform Readiness.
3. Open Review Queue and review the EOD candidate list for the selected
   `latest_market_date`.
4. Open a candidate stock and review Evidence Digest, related News, Research
   Reports, and generated Reports.
5. Use News and Reports to inspect source context, then return to the stock or
   Review Queue with the same date context.
6. Open EOD Monitor to compare the market snapshot, candidate pressure, and
   local EOD conditions for the same operating date.
7. Use Data Explorer, Factor Lab, Backtest Lab, and Strategy Validation only
   for deeper local review. They are supporting workspaces, not real-time
   decision automation.

## Troubleshooting

- API does not respond: confirm `/Users/xiwei/stock_research/.venv/bin/stock-research
  dashboard-api --host 127.0.0.1 --port 8765` is still running and that no
  other process owns port `8765`.
- Frontend does not load: run `cd dashboard && pnpm dev` and open
  `http://127.0.0.1:5174`.
- Readiness is `missing_data`: check whether the daily pipeline completed and
  whether `latest_market_date` is present in `/api/platform/readiness`.
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
  `/api/platform/readiness` `latest_market_date`; this dashboard does not
  continuously stream intraday updates.

## Acceptance Checks

Before handing the local dashboard to an operator:

- API starts on `127.0.0.1:8765`.
- Frontend opens on `http://127.0.0.1:5174`.
- `/api/platform/readiness` returns JSON with `mode: eod_local` and a
  meaningful `latest_market_date`.
- Home shows Platform Readiness without blocking the rest of the dashboard.
- Review Queue opens and either shows candidates or a clear empty state for the
  selected EOD date.
- News, Reports, Review Queue, and EOD Monitor are reachable from navigation.
- Stock detail preserves date and asset context when moving to News or Reports.
- The operator understands the dashboard is EOD-local rather than real-time.

## EOD Manifest Smoke

Run the local EOD pipeline with an explicit output directory:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli run-stock-daily-data-pipeline \
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
