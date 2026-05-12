# Vectorized TopN Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a project-native vectorbt-style TopN rotation engine that backtests `factor.stock_score_daily` candidates with daily or weekly rebalance, equal weights, transaction costs, max holdings, turnover, and equity output.

**Architecture:** Keep the first implementation independent from the existing account-level `portfolio_backtest.py`. The engine accepts score and price DataFrames, computes close-to-close forward portfolio returns from scores known at the rebalance date, and returns equity, rebalance positions, and summary frames. A small database adapter loads `factor.stock_score_daily` and `market_daily_bar` inputs without adding new runtime dependencies.

**Tech Stack:** Python, pandas, pytest, PostgreSQL through existing `stock_research.db` helpers.

---

## File Structure

- Create `src/stock_research/vectorized_topn_backtest.py`: dataclasses, core vectorized engine, summary metrics, and DB input loader.
- Create `tests/test_vectorized_topn_backtest.py`: unit tests for daily rebalance, weekly rebalance, costs, turnover, max holdings, and DB query shape.
- Modify `docs/astock-research-platform-v1.md`: record Track 3 first-slice progress.

Do not modify `src/stock_research/cli.py` in this slice because it currently has unrelated uncommitted changes in the working tree.

## Task 1: Core Daily Rebalance Engine

**Files:**
- Create: `tests/test_vectorized_topn_backtest.py`
- Create: `src/stock_research/vectorized_topn_backtest.py`

- [ ] **Step 1: Write failing daily rebalance test**

Test behavior: scores at date `t` select TopN holdings for close-to-close returns from `t` to the next trading date. First rebalance has turnover `1.0`; replacing one of two names has turnover `1.0`; transaction cost is `turnover * transaction_cost_bps / 10000`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_vectorized_topn_backtest.py::test_run_vectorized_topn_backtest_daily_rebalances_topn_with_costs -q`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement minimal engine**

Add:
- `VectorizedTopNConfig`
- `VectorizedTopNResult`
- `run_vectorized_topn_backtest`
- helpers for date normalization, price return matrix, rebalance dates, equal weights, turnover, drawdown, and summary.

- [ ] **Step 4: Run daily rebalance test**

Run: `.venv/bin/pytest tests/test_vectorized_topn_backtest.py::test_run_vectorized_topn_backtest_daily_rebalances_topn_with_costs -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/vectorized_topn_backtest.py tests/test_vectorized_topn_backtest.py docs/superpowers/plans/2026-05-10-vectorized-topn-backtest.md
git commit -m "Add vectorized TopN backtest engine"
```

## Task 2: Weekly Rebalance And Max Holdings

**Files:**
- Modify: `tests/test_vectorized_topn_backtest.py`
- Modify: `src/stock_research/vectorized_topn_backtest.py`

- [ ] **Step 1: Write failing weekly rebalance test**

Test behavior: `rebalance_frequency="weekly"` rebalances only on the first available trading date of each ISO week and keeps the prior target weights on non-rebalance dates.

- [ ] **Step 2: Write failing max holdings test**

Test behavior: `max_positions` caps holdings even when `top_n` is larger.

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_vectorized_topn_backtest.py -q`

Expected: FAIL on weekly or max holdings behavior until implemented.

- [ ] **Step 4: Implement weekly and max holdings behavior**

Update `_rebalance_dates` and `_target_weights_for_date`.

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest tests/test_vectorized_topn_backtest.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/stock_research/vectorized_topn_backtest.py tests/test_vectorized_topn_backtest.py
git commit -m "Support weekly vectorized TopN rebalance"
```

## Task 3: Database Input Adapter

**Files:**
- Modify: `tests/test_vectorized_topn_backtest.py`
- Modify: `src/stock_research/vectorized_topn_backtest.py`

- [ ] **Step 1: Write failing DB loader test**

Test behavior: `load_vectorized_topn_inputs` queries `factor.stock_score_daily` and `market_daily_bar`, returning score and price DataFrames.

- [ ] **Step 2: Run loader test to verify it fails**

Run: `.venv/bin/pytest tests/test_vectorized_topn_backtest.py::test_load_vectorized_topn_inputs_queries_scores_and_prices -q`

Expected: FAIL because the loader does not exist.

- [ ] **Step 3: Implement loader**

Use existing `connect` and `fetch_all`. Query score rows by `score_version`, `start_date`, `end_date`; query `market_daily_bar` close prices by `adjust_type`, `start_date`, `end_date`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_vectorized_topn_backtest.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/vectorized_topn_backtest.py tests/test_vectorized_topn_backtest.py
git commit -m "Add vectorized TopN input loader"
```

## Task 4: Documentation And Verification

**Files:**
- Modify: `docs/astock-research-platform-v1.md`

- [ ] **Step 1: Update platform doc**

Add a current-progress bullet under Stage 6 for the first vectorized TopN engine slice.

- [ ] **Step 2: Run focused tests**

Run: `.venv/bin/pytest tests/test_vectorized_topn_backtest.py -q`

Expected: PASS.

- [ ] **Step 3: Run full tests**

Run: `.venv/bin/pytest -q`

Expected: PASS.

- [ ] **Step 4: Commit docs**

Run:

```bash
git add docs/astock-research-platform-v1.md
git commit -m "Document vectorized TopN backtest progress"
```

- [ ] **Step 5: Push**

Run: `git push`

Expected: branch pushes cleanly.

## Self-Review

- Spec coverage: Track 3 first slice covers daily/weekly rebalance, transaction costs, equal weights, max holdings, turnover, equity curve, and DB input loading.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: public names are `VectorizedTopNConfig`, `VectorizedTopNResult`, `run_vectorized_topn_backtest`, and `load_vectorized_topn_inputs`.
