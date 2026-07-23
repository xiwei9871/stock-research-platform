# Theme Company Yanbaoke Quota Design

## Goal

Use the remaining 474 July Yanbaoke downloads to improve readable-PDF coverage for companies mapped by the production Theme Research dashboard.

## Authoritative Inputs

- Theme and company mappings: production Theme Research HTTP APIs under `/api/research/theme-decomposition`.
- Existing report and readable-PDF coverage: `research.stock_report_source` joined to `research.stock_report_event`.
- Download discovery and PDF retrieval: existing functions in `stock_research.yanbaoke_reports`.
- Existing downloaded UUIDs: `metadata.yanbaoke.uuid` in `research.stock_report_source` plus prior manifests.

## Allocation

The production mapping currently contains 27 themes, 264 mappings, and 225 unique companies. Allocate the 474 successful downloads as follows:

- 394 primary coverage slots: raise P0 companies (priority score >= 90) to three readable PDFs in 120 days, P1 companies (80-89.99) to two, and P2/P3 companies to one.
- 28 multi-theme depth slots: add one report to the highest-priority companies mapped to more than one theme.
- 28 theme-scarcity slots: add one report to high-priority companies in themes whose average 120-day readable-PDF coverage is lowest.
- 24 replacement slots: maintain an ordered reserve used only when a primary candidate fails, is unavailable, or duplicates an existing report. Unused reserve is released to the highest-priority depth candidates before month end.

The planner may emit up to 550 unique candidate UUIDs, but the downloader must stop immediately after 474 successful downloads.

## Candidate Rules

- Prefer initiation, company deep dive, and industry deep dive reports, then annual/quarterly and material-event reviews.
- Reject morning notes, daily summaries, pure market recaps, missing PDFs, existing UUIDs, and normalized title/broker/date duplicates.
- Limit one same-category report from the same broker for a company within 60 days.
- Limit a normal company to four selected reports; allow five only for multi-theme companies with priority >= 90.
- Limit one broker to 15% of the 474-success target.
- Rank by allocation bucket, coverage deficit, company priority, multi-theme relevance, report type, broker tier, recency, and page count.

## Outputs

Write a dated package under `outputs/research/theme_company_yanbaoke_20260723/` containing:

- `theme_company_mappings.csv`
- `theme_company_report_coverage.csv`
- `yanbaoke_discovered_candidates.csv`
- `yanbaoke_download_queue_474.csv`
- `yanbaoke_replacement_queue.csv`
- `yanbaoke_downloads.csv`
- `import/` artifacts
- `run_summary.json`
- `run_report.md`

## Execution And Verification

Discovery is read-only and must not consume download quota. Before the full run, validate the queue totals, UUID uniqueness, existing-UUID exclusion, company caps, and broker cap. Download in checkpointed batches and persist the manifest after every five attempts. Import successful PDFs with `write_db=True`, then verify that successful download count, PDF file count, unique UUID count, imported source/event count, and database-readable report count agree.

## Guardrails

- Never print or persist the API key.
- Do not modify theme mappings, trading signals, admissions, or strategy logic.
- Do not exceed 474 successful downloads.
- Preserve failed attempts and exclusion reasons for audit.
