# 02 — Report Metadata Batch-1 Approval Package (M0.6)

Date: 2026-10-20. Branch: `audit/tech-strategy-m0-20261019` @ `1149c763`.
Scope: **first batch = 29 reports only** — the `candidate_ready_for_separate_approval`
rows of `docs/research_upgrade/01_report_metadata_dry_run_diff.csv` (catalogue date ==
PDF first-two-page date token). 11 conflicts + 7 no-cover-date stay in the manual queue.

## Verdict: READY-FOR-APPROVAL — package complete; **no production write performed**

## Package contents — `outputs/research/report_metadata_batch1_approval_20261020/`

| Artifact | Purpose |
|---|---|
| `batch1_manifest.json` | 29 `report_id`s + sha256 of both backup snapshots |
| `batch1_source_backup_snapshot.csv` | field-level backup: `stock_report_source` (report_id, publish_date, source_url, metadata) — **all `publish_date` currently NULL**, verified by live SELECT |
| `batch1_event_backup_snapshot.csv` | field-level backup: `stock_report_event` (report_id, ts_code, report_date) — 29 rows (1 event/report), all `report_date` NULL |
| `batch1_update.sql` | transaction: `BEGIN` → 29×2 UPDATEs (`publish_date`, `report_date`, `metadata.date_remediation` audit tag) → verification SELECTs → **COMMIT intentionally commented** for interactive run |
| `batch1_rollback.sql` | restore both columns to NULL + drop the audit tag; ends with COMMIT |

## Field semantics (guardrail honored)

- `publish_date` / `report_date` := the report's **true publication date** (catalogue ==
  cover double-verified), required by `_load_report_keyword_support`'s
  `e.report_date >= '2024-01-01'` filter.
- `available_at` := ingestion/observation time. **The DB has no `available_at` column** —
  the dry-run records `local PDF file mtime` only as a first-observation proxy and states
  this explicitly. Backfilling historical `publish_date` does **not** leak reports into
  historical PIT: backtests consume research artifacts keyed by build date, not by
  `publish_date`; no code path reads these rows for as-of-date replay.

## Before / after evidence consumption

| Metric | Before | After batch-1 |
|---|---|---|
| `stock_report_source.publish_date` non-null (29 scope) | 0 | 29 |
| `stock_report_event.report_date` non-null | 0 | 29 |
| Eligible for `report_date >= 2024-01-01` keyword query | 0 | 29 |
| Remaining gated: 11 conflict + 7 no-cover-date | 18 | 18 (unchanged, manual queue) |

## Execution protocol (on approval)

1. Re-run backup SELECTs, diff against the stored snapshots — abort if any row drifted.
2. `psql` interactive: run `batch1_update.sql` up to (not incl.) `COMMIT`; verify the two
   verification SELECTs return 29 / 29 → `COMMIT`.
3. Re-run `_load_report_keyword_support` count + spot-check 5 titles; record
   after-counts into the dry-run table's `hypothetical_keyword_query_eligible_if_approved`.
4. Rollback path: `batch1_rollback.sql` restores NULLs (original state) — instant, no
   data loss risk since columns were NULL before.
5. Auto-trade stays `false`; `public_access` untouched.

## Still manual (not in this batch)

- 11 `cover_date_other`: catalogue vs cover date conflict → human adjudicates per report.
- 7 `no_cover_date_found`: scanned/no-text-layer PDFs → human reads cover image.
- Nothing else in `stock_report_*` is touched; formal signals/admission unaffected.
