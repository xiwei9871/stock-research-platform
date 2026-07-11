# Theme Research Workflow Integration v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Phase 10 by exposing one reviewed, research-only Theme Research context in Daily Review, Watchlist, and Stock Workspace, then verify Phases 1-10 against authoritative evidence.

**Architecture:** Add a focused PostgreSQL-backed read-model service and reuse it in existing backend payloads. Keep Theme Research independent from scoring and the tech-bottleneck dashboard, fail closed on review eligibility, and add a machine-readable P1-P10 verifier.

**Tech Stack:** Python 3.12, FastAPI, psycopg, PostgreSQL, pytest, React, TypeScript, Vitest, Playwright.

---

### Task 1: Asset Theme Research Context

**Files:**
- Create: `src/stock_research/dashboard/theme_research_context.py`
- Create: `tests/test_dashboard_theme_research_context.py`

- [ ] Write failing tests for canonical asset normalization, reviewed mapping eligibility, evidence hydration, empty mappings, fail-closed rows, stable guardrails, and conservative driver assessment.
- [ ] Run `rtk pytest tests/test_dashboard_theme_research_context.py -q` and confirm failures are caused by the missing service.
- [ ] Implement `load_asset_theme_context`, compact SQL read models, accepted-source filtering, reviewed-claim filtering, and guardrails.
- [ ] Re-run the focused tests and confirm all pass.
- [ ] Commit only Task 1 files with `feat: add reviewed theme research context`.

### Task 2: Watchlist And Asset Profile Integration

**Files:**
- Modify: `src/stock_research/dashboard/watchlist.py`
- Modify: `src/stock_research/dashboard/asset_profile.py`
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_dashboard_watchlist.py`
- Modify: `tests/test_dashboard_asset_profile.py`
- Create: `tests/test_dashboard_theme_research_context_api.py`

- [ ] Write failing tests proving watchlist item order and signal fields remain byte-for-byte stable while context is added.
- [ ] Write failing tests proving asset profiles and the dedicated endpoint expose the same context.
- [ ] Run the focused tests and confirm expected failures.
- [ ] Add batch context enrichment, asset profile integration, and `GET /api/assets/{asset_id}/theme-research-context`.
- [ ] Re-run focused tests and existing watchlist/asset-profile tests.
- [ ] Commit Task 2 files with `feat: integrate theme context into stock workflows`.

### Task 3: Daily Review Digest And Theme Updates

**Files:**
- Modify: `src/stock_research/dashboard/theme_research_context.py`
- Modify: `src/stock_research/dashboard/daily_review_lite.py`
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_dashboard_theme_research_context.py`
- Modify: `tests/test_dashboard_daily_review_lite.py`

- [ ] Write failing tests for reviewed update filtering, compact digest counts, deterministic ordering, invalid date/limit handling, and Daily Review partial degradation.
- [ ] Run focused tests and confirm expected failures.
- [ ] Implement `list_theme_research_updates`, `build_daily_theme_research_digest`, the Daily Review section, and the updates endpoint.
- [ ] Re-run focused tests and Daily Review artifact round-trip tests.
- [ ] Commit Task 3 files with `feat: add theme research daily digest and updates`.

### Task 4: Dashboard Types And API Client

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/tests/client.test.ts`

- [ ] Write failing client/type tests for context fields and the dedicated context and updates endpoints.
- [ ] Run `rtk pnpm --dir dashboard test -- client.test.ts --run` and confirm expected failures.
- [ ] Add stable TypeScript types and fetch functions.
- [ ] Re-run the focused Vitest test.
- [ ] Commit Task 4 files with `feat: add theme research workflow client`.

### Task 5: Daily Review And Watchlist UI

**Files:**
- Modify: `dashboard/src/components/DailyReviewLiteWorkspace.tsx`
- Modify: `dashboard/src/components/WatchlistWorkspace.tsx`
- Modify: `dashboard/tests/daily-review-lite-workspace.test.tsx`
- Modify: `dashboard/tests/watchlist-workspace.test.tsx`

- [ ] Write failing UI tests for reviewed badges, node scores, evidence-gap language, navigation, and empty context.
- [ ] Run the two focused Vitest files and confirm expected failures.
- [ ] Render compact unframed Theme Research context without changing existing workflow controls.
- [ ] Re-run the focused tests and accessibility assertions.
- [ ] Commit Task 5 files with `feat: show theme context in review workflows`.

### Task 6: Stock Workspace UI

**Files:**
- Create: `dashboard/src/components/stock-workspace/ThemeResearchContextSection.tsx`
- Create: `dashboard/tests/theme-research-context-section.test.tsx`
- Modify: `dashboard/src/components/StockWorkspace.tsx`
- Modify: `dashboard/tests/stock-workspace.test.tsx`

- [ ] Write failing component tests for reviewed context, evidence gaps, no-mapping state, dashboard navigation, and research-only guardrails.
- [ ] Run the focused Vitest files and confirm expected failures.
- [ ] Implement the focused section and integrate it with the current Stock Workspace layout without overwriting unrelated local changes.
- [ ] Re-run focused and Stock Workspace regression tests.
- [ ] Commit Task 6 files with `feat: add stock theme research context`.

### Task 7: P1-P10 Verifier

**Files:**
- Create: `src/stock_research/theme_research_phase_verifier.py`
- Create: `tests/test_theme_research_phase_verifier.py`
- Modify: `src/stock_research/cli.py`
- Create: `scripts/verify_theme_research_p1_p10.sh`

- [ ] Write failing tests for requirement-level statuses, authoritative evidence details, the declared Phase 2B gap, failed checks, JSON output, and Markdown output.
- [ ] Run focused tests and confirm expected failures.
- [ ] Implement offline checks for P1-P8, PostgreSQL checks for P9, workflow/API contract checks for P10, and `theme-research verify-p1-p10` CLI wiring.
- [ ] Re-run focused tests and execute the verifier against the test database.
- [ ] Commit Task 7 files with `feat: verify theme research phases one through ten`.

### Task 8: Documentation And Roadmap Reconciliation

**Files:**
- Modify: `docs/theme_driven_research_engine_roadmap.md`
- Create: `docs/theme_research_workflow_integration_v1.md`
- Modify: `docs/theme_research_database_v1.md`

- [ ] Correct the stale Phase 9 status and deferred-language contradiction.
- [ ] Mark Phase 10 complete only after verification evidence exists.
- [ ] Document routes, payload guardrails, failure behavior, verifier commands, and the explicit Phase 2B evidence gap.
- [ ] Run a placeholder and contradiction scan with `rtk rg -n "TBD|TODO|Phase 9.*Planned|Phase 9.*deferred" docs/theme_*`.
- [ ] Commit documentation with `docs: complete theme research workflow roadmap`.

### Task 9: Full Verification And Independent Review

**Files:**
- Modify only files required by verified defects.

- [ ] Run focused Python tests for Theme Research context, API, Daily Review, Watchlist, asset profile, and verifier.
- [ ] Run the full Theme Research Python test set and dedicated PostgreSQL integration suite.
- [ ] Run Dashboard Vitest, TypeScript build, and Playwright Theme Research workflow tests.
- [ ] Start or reuse the local dashboard and perform authenticated production DB smoke calls for themes, one mapped stock, Daily Review, Watchlist, and updates.
- [ ] Run `rtk git diff --check` and inspect exact staged scope.
- [ ] Request independent code review; fix High and Medium findings through failing tests first.
- [ ] Run the final P1-P10 verifier and preserve its JSON and Markdown output under the documented reports directory.
- [ ] Commit verified fixes and final evidence without staging unrelated user changes.

