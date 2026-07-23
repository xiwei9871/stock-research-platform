# Theme Company Yanbaoke Quota Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate the approved 474-report Theme Research company queue, download exactly 474 successful Yanbaoke PDFs when enough valid candidates exist, import them, and verify the resulting coverage.

**Architecture:** Add a focused planning script that reads production theme APIs and the local research database, computes deterministic company quota slots, discovers and scores Yanbaoke candidates, and writes auditable CSV queues. Reuse the existing direct UUID downloader and Yanbaoke importer for external mutation and database writes.

**Tech Stack:** Python, pandas, PostgreSQL, production Theme Research JSON APIs, existing Yanbaoke search/download/import functions, pytest.

---

### Task 1: Quota Planner Rules

**Files:**
- Create: `tests/test_theme_company_yanbaoke_quota.py`
- Create: `scripts/run_theme_company_yanbaoke_quota.py`

- [ ] Write failing tests for priority-band targets, the 394/28/28/24 allocation, UUID/title dedupe, company caps, and the 15% broker cap.
- [ ] Run `rtk .venv/bin/pytest tests/test_theme_company_yanbaoke_quota.py -q` and confirm the tests fail because the planner does not exist.
- [ ] Implement pure allocation and candidate-selection functions with injected data inputs.
- [ ] Re-run the focused tests and confirm all pass.

### Task 2: Formal Inventory And Discovery

**Files:**
- Create package: `outputs/research/theme_company_yanbaoke_20260723/`

- [ ] Fetch all production theme mappings and write `theme_company_mappings.csv`.
- [ ] Query 30/60/90/120-day index and readable-PDF counts and write `theme_company_report_coverage.csv`.
- [ ] Search Yanbaoke for each mapped company without downloading and persist all qualified candidates.
- [ ] Build the formal and replacement queues and write a dry-run summary.

### Task 3: Queue Audit

- [ ] Verify queue UUID uniqueness and exclusion of existing downloaded UUIDs.
- [ ] Verify allocation counts, company caps, report-type exclusions, and broker cap.
- [ ] Require at least 474 valid candidate UUIDs before starting the full download; otherwise continue discovery with a 365-day fallback window while preserving the preferred 120-day ranking.

### Task 4: Download And Import

- [ ] Run the direct UUID downloader with `--target-successes 474`, a bounded replacement attempt pool, checkpoint writes every five attempts, per-company cap five, and an effective broker cap of 71 reports.
- [ ] Import successful downloads with `import_yanbaoke_report_downloads(..., write_db=True, feature_trade_date="2026-07-23")`.
- [ ] Preserve download and import manifests under the dated package.

### Task 5: Completion Audit

- [ ] Verify `downloaded == unique_uuid == existing_pdf_files == 474` when sufficient candidates are available.
- [ ] Verify imported report source/event rows and database readable-PDF rows for the downloaded UUIDs.
- [ ] Recompute mapped-company coverage and write `run_summary.json` and `run_report.md` with before/after figures, failures, exclusions, and remaining gaps.
- [ ] Run focused tests, Python compilation, CSV invariants, and `git diff --check` before reporting completion.
