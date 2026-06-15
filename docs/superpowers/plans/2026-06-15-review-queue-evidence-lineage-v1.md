# Review Queue Evidence Lineage v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Review Queue lineage and Evidence Digest partial-evidence sections without changing strategy logic or HomeCockpit layout.

**Architecture:** Extend the dashboard read model layer only. `review_queue.py` derives item lineage from TopN rows, embedded digest metadata, and Batch A manifest. `evidence_digest.py` keeps legacy fields while adding structured sections and digest status. Frontend changes are limited to API types.

**Tech Stack:** Python 3.14, FastAPI dashboard modules, pytest, TypeScript API types, Vitest, Vite build.

---

### Task 1: Evidence Digest Sections

**Files:**
- Modify: `tests/test_dashboard_evidence_digest.py`
- Modify: `src/stock_research/dashboard/evidence_digest.py`

- [ ] **Step 1: Write failing tests**

Add tests that assert digest responses contain `digest_key`, `overall_status`, `sections`, `missing_evidence`, `partial_evidence`, `lineage`, and stable section statuses for available, partial, missing, and unavailable evidence.

- [ ] **Step 2: Run red tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_evidence_digest.py -q
```

Expected: new tests fail because the response lacks structured section fields.

- [ ] **Step 3: Implement sections**

Add helper functions in `evidence_digest.py`:

- `_section(...)`
- `_build_sections(...)`
- `_section_status_from_optional_source(...)`
- `_overall_status(...)`
- `_digest_key(...)`
- `_manifest_context(...)`

Keep legacy fields unchanged.

- [ ] **Step 4: Run green tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_evidence_digest.py -q
```

Expected: all digest tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_dashboard_evidence_digest.py src/stock_research/dashboard/evidence_digest.py
git commit -m "feat: add evidence digest sections"
```

### Task 2: Review Queue Lineage

**Files:**
- Modify: `tests/test_dashboard_review_queue.py`
- Modify: `src/stock_research/dashboard/review_queue.py`

- [ ] **Step 1: Write failing tests**

Add tests that assert each item includes lineage fields: `run_id`, `latest_trade_date`, `generated_at`, `source_type`, `source_name`, `source_rank`, `topn_rank`, `score_components`, `strategy_run_id`, `digest_key`, `digest_url_path`, `stock_workspace_url_path`, `evidence_status`, `missing_evidence_count`, `partial_evidence_count`, `warnings_count`, and `manifest_modules`.

- [ ] **Step 2: Run red tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_review_queue.py -q
```

Expected: new tests fail because lineage fields are absent.

- [ ] **Step 3: Implement lineage**

Extend `_queue_item(...)` to derive lineage from score rows and digest fields. Read latest manifest context once in `build_review_queue(...)`; if unavailable, keep `manifest_modules` empty and add a queue-level warning.

- [ ] **Step 4: Run green tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_review_queue.py -q
```

Expected: all review queue tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_dashboard_review_queue.py src/stock_research/dashboard/review_queue.py
git commit -m "feat: add review queue lineage"
```

### Task 3: API Shape And Frontend Type Compatibility

**Files:**
- Modify: `tests/test_dashboard_app.py`
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Write failing tests**

Add dashboard API and client/type assertions for expanded Review Queue and Evidence Digest shape.

- [ ] **Step 2: Run red tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_app.py -q
cd dashboard && pnpm exec vitest run --exclude "**/*.spec.ts" tests/client.test.ts
```

Expected: type/client tests fail until API types include new fields.

- [ ] **Step 3: Implement type compatibility**

Update only API types. Do not change HomeCockpit or Strategy Command Center components.

- [ ] **Step 4: Run green tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_app.py -q
cd dashboard && pnpm exec vitest run --exclude "**/*.spec.ts" tests/client.test.ts
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_dashboard_app.py dashboard/src/api/types.ts dashboard/tests/client.test.ts
git commit -m "test: cover lineage api shapes"
```

### Task 4: Final Verification

**Files:**
- No production edits unless focused tests identify a Batch B regression.

- [ ] **Step 1: Run backend focused suite**

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_review_queue.py \
  tests/test_dashboard_evidence_digest.py \
  tests/test_dashboard_app.py \
  tests/test_dashboard_readiness.py -q
```

- [ ] **Step 2: Run frontend focused suite**

```bash
cd dashboard && pnpm exec vitest run --exclude "**/*.spec.ts" \
  tests/client.test.ts tests/review-queue-workspace.test.tsx tests/stock-workspace.test.tsx
```

- [ ] **Step 3: Run dashboard build**

```bash
cd dashboard && pnpm build
```

- [ ] **Step 4: Commit verification-only docs if needed**

Only commit additional docs if a runbook change is required by observed behavior.
