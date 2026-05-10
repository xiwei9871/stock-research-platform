# Approval Aware Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make factor scoring able to enforce the factor evaluation gate by loading only approved factors when explicitly requested.

**Architecture:** Extend `factor_store.load_factor_daily` with `approved_only` and `score_version` parameters. The default path stays unchanged for compatibility. When `approved_only=True`, the query joins `factor.factor_approval` and requires `status='approved'`, matching `factor_name`, `calc_version`, and `score_version`. `score_stored_factor_daily` gets the same optional switch and passes it through.

**Tech Stack:** Python, pandas, pytest, PostgreSQL SQL through existing `fetch_all`.

---

## File Structure

- Modify `src/stock_research/factor_store.py`: approved-only loader and score passthrough.
- Modify `tests/test_factor_store.py`: query shape and score passthrough tests.
- Modify `docs/daily-factor-pipeline-runbook.md`: document approval-aware scoring guardrail.

Do not modify `src/stock_research/cli.py` in this slice because it currently has unrelated uncommitted changes in the working tree.

## Task 1: Approved Factor Loader

**Files:**
- Modify: `tests/test_factor_store.py`
- Modify: `src/stock_research/factor_store.py`

- [ ] **Step 1: Write failing approved loader test**

Test behavior: `load_factor_daily(..., approved_only=True, score_version="manual_v1")` joins `factor.factor_approval` and passes score version in query params.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_factor_store.py::test_load_factor_daily_can_filter_to_approved_factors -q`

Expected: FAIL because `approved_only` is not accepted.

- [ ] **Step 3: Implement loader switch**

Default SQL remains unchanged. Approved SQL adds an inner join against `factor.factor_approval`.

- [ ] **Step 4: Run factor store tests**

Run: `.venv/bin/pytest tests/test_factor_store.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/factor_store.py tests/test_factor_store.py docs/superpowers/plans/2026-05-10-approval-aware-scoring.md
git commit -m "Add approval aware factor loading"
```

## Task 2: Score Passthrough

**Files:**
- Modify: `tests/test_factor_store.py`
- Modify: `src/stock_research/factor_store.py`

- [ ] **Step 1: Write failing score passthrough test**

Test behavior: `score_stored_factor_daily(..., approved_only=True)` passes `approved_only=True` and `score_version` into `load_factor_daily`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_factor_store.py::test_score_stored_factor_daily_can_require_approved_factors -q`

Expected: FAIL because `score_stored_factor_daily` does not accept `approved_only`.

- [ ] **Step 3: Implement passthrough**

Add the parameter to `score_stored_factor_daily` and pass it to `load_factor_daily`.

- [ ] **Step 4: Run factor store tests**

Run: `.venv/bin/pytest tests/test_factor_store.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/factor_store.py tests/test_factor_store.py
git commit -m "Allow scoring approved factors only"
```

## Task 3: Documentation And Verification

**Files:**
- Modify: `docs/daily-factor-pipeline-runbook.md`

- [ ] **Step 1: Update runbook**

Explain that scoring code can enforce approval via `approved_only=True`, while the current CLI path remains default-compatible until main CLI cleanup.

- [ ] **Step 2: Run focused tests**

Run: `.venv/bin/pytest tests/test_factor_store.py -q`

Expected: PASS.

- [ ] **Step 3: Run full tests**

Run: `.venv/bin/pytest -q`

Expected: PASS.

- [ ] **Step 4: Commit docs**

Run:

```bash
git add docs/daily-factor-pipeline-runbook.md
git commit -m "Document approval aware scoring"
```

- [ ] **Step 5: Push**

Run: `git push`

Expected: branch pushes cleanly.

## Self-Review

- Spec coverage: adds enforcement hook without breaking default daily pipeline.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: public parameter is `approved_only`.
