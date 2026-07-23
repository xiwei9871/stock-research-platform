# Research Report Reader V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users click a research report and read its PDF in the dashboard when a safe local PDF is available.

**Architecture:** Add a backend document resolver that maps a report id to safe document metadata and serves local PDF files only from whitelisted report directories. Upgrade the Research Reports workspace detail panel to load that document metadata and render an inline PDF viewer or a clear source-only fallback.

**Tech Stack:** FastAPI, FileResponse, React, TypeScript, browser-native PDF iframe, pytest, Vitest.

---

### Task 1: Backend Document Endpoints

**Files:**
- Modify: `src/stock_research/dashboard/research_reports.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_research_reports.py`

- [ ] Add failing tests for `load_research_report_document`, safe PDF URL generation, and PDF route wiring.
- [ ] Implement local PDF resolution from `metadata.yanbaoke.local_pdf_path` and `file://` source URLs.
- [ ] Serve PDFs through `/api/research-reports/{report_id}/pdf` with inline `application/pdf`.

### Task 2: Frontend Reader Panel

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/src/components/ResearchReportsWorkspace.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/research-reports-workspace.test.tsx`

- [ ] Add failing test that selecting a report loads document metadata and renders an iframe PDF viewer.
- [ ] Add failing test that a report without PDF shows a clear fallback and source link.
- [ ] Implement document fetch, loading/error state, PDF iframe, and fallback.

### Task 3: Verification

**Files:**
- Test only.

- [ ] Run targeted backend tests.
- [ ] Run targeted frontend tests.
- [ ] Run `pnpm build`.
- [ ] Manually verify one real report endpoint and page behavior locally.
