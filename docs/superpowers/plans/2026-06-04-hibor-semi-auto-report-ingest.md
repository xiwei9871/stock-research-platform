# Hibor Semi-Auto Report Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a semi-automatic Hibor report workflow where the user keeps Hibor logged in and scripts generate download queues, import downloaded PDFs, parse fields, and optionally write to the existing research tables.

**Architecture:** Add a focused `hibor_reports` module for queue generation, filename parsing, local PDF source/event construction, and download-directory watching. Reuse existing `research.stock_report_source`, `research.stock_report_event`, `upsert_stock_report_sources_events`, and `stock-report-pdf-field-backfill` instead of creating separate storage.

**Tech Stack:** Python, pandas, pypdf, existing `stock_research` CLI and PostgreSQL upsert helpers.

---

### Task 1: Local PDF Support

**Files:**
- Modify: `src/stock_research/stock_report_pdf_backfill.py`
- Test: `tests/test_stock_report_pdf_backfill.py`

- [ ] Add a failing test proving `fetch_pdf_text()` accepts a local PDF path.
- [ ] Update `fetch_pdf_text()` to read `file://` and local paths with `pypdf`.
- [ ] Run the focused PDF tests.

### Task 2: Hibor Import Module

**Files:**
- Create: `src/stock_research/hibor_reports.py`
- Test: `tests/test_hibor_reports.py`

- [ ] Add failing tests for Hibor filename parsing.
- [ ] Add failing tests for building `hibor_manual` source/event rows.
- [ ] Add failing tests for watch/import behavior over a directory.
- [ ] Implement the minimal module functions.
- [ ] Run focused Hibor tests.

### Task 3: CLI Wiring

**Files:**
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_hibor_reports.py`

- [ ] Add failing CLI dispatch tests for queue generation and PDF import.
- [ ] Wire `build-hibor-download-queue`, `import-hibor-report-pdfs`, and `watch-hibor-downloads`.
- [ ] Run focused CLI tests.

### Task 4: Verification

**Files:**
- Existing tests only.

- [ ] Run Hibor and PDF focused tests.
- [ ] Run CLI help smoke for the new commands.
- [ ] Run a dry sample import against the provided Eastmoney-style Hibor PDF path without writing DB.
