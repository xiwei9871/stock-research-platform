# Sector Strength Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Stage 7 sector strength report that ranks industry groups for daily monitoring.

**Architecture:** Implement a report module under `stock_research.reports`. Keep calculation pure pandas, loading separate from calculation, and output separate from loading. The first slice uses `market.industry_daily_bar` close and amount data to calculate 5-day return, 20-day return, amount ratio, and composite strength rank.

**Tech Stack:** Python, pandas, pytest, existing PostgreSQL helpers.

---

## File Structure

- Create `src/stock_research/reports/sector_strength_report.py`: calculation, DB loader, and writer.
- Create `tests/test_sector_strength_report.py`: unit tests for calculation, writer, and loader query shape.
- Modify `docs/daily-factor-pipeline-runbook.md`: document report generation helper.
- Modify `docs/astock-research-platform-v1.md`: record Stage 7 progress.

Do not modify `src/stock_research/cli.py` in this slice because it currently has unrelated uncommitted changes in the working tree.

## Task 1: Sector Strength Calculation

**Files:**
- Create: `tests/test_sector_strength_report.py`
- Create: `src/stock_research/reports/sector_strength_report.py`

- [ ] **Step 1: Write failing calculation test**

Test behavior: `calc_sector_strength` returns latest rows ranked by composite strength, with `ret_5d`, `ret_20d`, `amount_ratio_5_20`, and `strength_score`.

- [ ] **Step 2: Run test to verify failure**

Run: `.venv/bin/pytest tests/test_sector_strength_report.py::test_calc_sector_strength_ranks_latest_industries -q`

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement calculation**

Normalize dates and numerics. Compute returns by industry code and amount ratio from 5-day mean over 20-day mean. Rank higher returns and amount ratio better.

- [ ] **Step 4: Run calculation tests**

Run: `.venv/bin/pytest tests/test_sector_strength_report.py -q`

Expected: PASS for calculation tests.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/reports/sector_strength_report.py tests/test_sector_strength_report.py docs/superpowers/plans/2026-05-10-sector-strength-report.md
git commit -m "Add sector strength calculation"
```

## Task 2: Writer And Loader

**Files:**
- Modify: `tests/test_sector_strength_report.py`
- Modify: `src/stock_research/reports/sector_strength_report.py`

- [ ] **Step 1: Write failing writer test**

Test behavior: `write_sector_strength_report` writes markdown and CSV with top sector rows.

- [ ] **Step 2: Write failing loader test**

Test behavior: `load_sector_strength_bars` queries `market.industry_daily_bar` with `industry_system` and date bounds.

- [ ] **Step 3: Run tests to verify failures**

Run: `.venv/bin/pytest tests/test_sector_strength_report.py -q`

Expected: FAIL until writer and loader exist.

- [ ] **Step 4: Implement writer and loader**

Use deterministic filenames: `sector_strength_<trade_date>_<industry_system>.md/csv`.

- [ ] **Step 5: Run focused tests**

Run: `.venv/bin/pytest tests/test_sector_strength_report.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/stock_research/reports/sector_strength_report.py tests/test_sector_strength_report.py
git commit -m "Add sector strength report writer"
```

## Task 3: Documentation And Verification

**Files:**
- Modify: `docs/daily-factor-pipeline-runbook.md`
- Modify: `docs/astock-research-platform-v1.md`

- [ ] **Step 1: Update docs**

Document that Stage 7 has a sector strength helper and how to call it from Python until CLI cleanup.

- [ ] **Step 2: Run focused tests**

Run: `.venv/bin/pytest tests/test_sector_strength_report.py -q`

Expected: PASS.

- [ ] **Step 3: Run full tests**

Run: `.venv/bin/pytest -q`

Expected: PASS.

- [ ] **Step 4: Commit docs and push**

Run:

```bash
git add docs/daily-factor-pipeline-runbook.md docs/astock-research-platform-v1.md
git commit -m "Document sector strength report"
git push
```

## Self-Review

- Spec coverage: implements Stage 7 sector strength reporting without adding CLI risk.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: public names are `calc_sector_strength`, `load_sector_strength_bars`, and `write_sector_strength_report`.
