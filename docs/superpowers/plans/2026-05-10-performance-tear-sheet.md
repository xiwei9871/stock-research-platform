# Performance Tear Sheet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add empyrical/pyfolio-style performance metrics and local tear sheet output for vectorized TopN backtest results.

**Architecture:** Keep metrics in a pure pandas module with no external runtime dependency. Keep report writing separate so strategy and backtest code can call it without coupling to file paths. The first slice writes markdown plus CSV files for metrics, equity curve, and positions; xlsx can be added later if the dependency boundary is approved.

**Tech Stack:** Python, pandas, pytest, existing `VectorizedTopNResult`.

---

## File Structure

- Create `src/stock_research/performance_metrics.py`: cumulative return, annual return, volatility, max drawdown, Sharpe, Sortino, Calmar, win rate, average holding days, annual turnover.
- Create `src/stock_research/performance_tearsheet.py`: markdown and CSV report writer for vectorized TopN results.
- Create `tests/test_performance_metrics.py`: metric behavior tests.
- Create `tests/test_performance_tearsheet.py`: report output tests.
- Modify `docs/astock-research-platform-v1.md`: record Track 5 first-slice progress.

Do not modify `src/stock_research/cli.py` in this slice because it currently has unrelated uncommitted changes in the working tree.

## Task 1: Performance Metrics

**Files:**
- Create: `tests/test_performance_metrics.py`
- Create: `src/stock_research/performance_metrics.py`

- [ ] **Step 1: Write failing metric test**

Test behavior: `calc_performance_metrics` consumes a vectorized equity curve and positions, returning cumulative return, annual return, annual volatility, max drawdown, Sharpe, Sortino, Calmar, win rate, average holding days, annual turnover, and periods.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_performance_metrics.py::test_calc_performance_metrics_reports_empyrical_style_metrics -q`

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement metrics**

Use period returns from `net_return`, equity from `equity`, drawdown from `drawdown`, turnover from `turnover`, and rebalance intervals from `positions.rebalance_date`.

- [ ] **Step 4: Run metric tests**

Run: `.venv/bin/pytest tests/test_performance_metrics.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/performance_metrics.py tests/test_performance_metrics.py docs/superpowers/plans/2026-05-10-performance-tear-sheet.md
git commit -m "Add performance metrics"
```

## Task 2: Tear Sheet Writer

**Files:**
- Create: `tests/test_performance_tearsheet.py`
- Create: `src/stock_research/performance_tearsheet.py`

- [ ] **Step 1: Write failing tear sheet test**

Test behavior: `write_performance_tearsheet` writes markdown, metrics CSV, equity CSV, and positions CSV for a `VectorizedTopNResult`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_performance_tearsheet.py::test_write_performance_tearsheet_writes_markdown_and_csv_outputs -q`

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement writer**

Create deterministic filenames from strategy id, start date, and end date. Include guardrail text that output is research only.

- [ ] **Step 4: Run tear sheet tests**

Run: `.venv/bin/pytest tests/test_performance_tearsheet.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/performance_tearsheet.py tests/test_performance_tearsheet.py
git commit -m "Add performance tear sheet writer"
```

## Task 3: Documentation And Verification

**Files:**
- Modify: `docs/astock-research-platform-v1.md`

- [ ] **Step 1: Update platform doc**

Add a current-progress bullet under performance analysis for the new metrics and tear sheet layer.

- [ ] **Step 2: Run focused tests**

Run: `.venv/bin/pytest tests/test_performance_metrics.py tests/test_performance_tearsheet.py -q`

Expected: PASS.

- [ ] **Step 3: Run full tests**

Run: `.venv/bin/pytest -q`

Expected: PASS.

- [ ] **Step 4: Commit docs**

Run:

```bash
git add docs/astock-research-platform-v1.md
git commit -m "Document performance tear sheet progress"
```

- [ ] **Step 5: Push**

Run: `git push`

Expected: branch pushes cleanly.

## Self-Review

- Spec coverage: covers Track 5 first slice except xlsx, which is explicitly deferred to avoid adding a spreadsheet dependency prematurely.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: public names are `calc_performance_metrics` and `write_performance_tearsheet`.
