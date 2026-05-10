# Vectorized Trade Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add trade-detail output to the vectorized TopN backtest engine so research reports can inspect rebalance orders, not only target positions.

**Architecture:** Treat trades as vectorized rebalance orders rather than account-level fills. Each rebalance emits one row per asset whose target weight changes, with previous weight, target weight, delta weight, side, turnover contribution, and transaction cost contribution. This keeps the engine fast and aligned with vectorbt-style signal matrices.

**Tech Stack:** Python, pandas, pytest.

---

## File Structure

- Modify `src/stock_research/vectorized_topn_backtest.py`: add `trades` to result and generate trade rows.
- Modify `tests/test_vectorized_topn_backtest.py`: verify trade detail rows.
- Modify `src/stock_research/performance_tearsheet.py`: write trades CSV when present while preserving current positions CSV.
- Modify `tests/test_performance_tearsheet.py`: verify trades CSV path when result includes trades.
- Modify `docs/astock-research-platform-v1.md`: record trade-detail output progress.

## Task 1: Vectorized Trade Rows

**Files:**
- Modify: `tests/test_vectorized_topn_backtest.py`
- Modify: `src/stock_research/vectorized_topn_backtest.py`

- [ ] **Step 1: Write failing trade-detail test**

Test behavior: first rebalance from cash emits buy rows; second rebalance emits sell/buy rows for changed weights. Costs are proportional to each row's absolute delta weight.

- [ ] **Step 2: Run test to verify failure**

Run: `.venv/bin/pytest tests/test_vectorized_topn_backtest.py::test_run_vectorized_topn_backtest_outputs_rebalance_trade_details -q`

Expected: FAIL because result has no `trades` attribute.

- [ ] **Step 3: Implement trade rows**

Add `TRADE_COLUMNS`, `trades` to `VectorizedTopNResult`, `_trade_rows_for_rebalance`, and append rows during rebalance.

- [ ] **Step 4: Run vectorized tests**

Run: `.venv/bin/pytest tests/test_vectorized_topn_backtest.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/vectorized_topn_backtest.py tests/test_vectorized_topn_backtest.py docs/superpowers/plans/2026-05-10-vectorized-trade-detail.md
git commit -m "Add vectorized TopN trade details"
```

## Task 2: Tear Sheet Trades CSV

**Files:**
- Modify: `tests/test_performance_tearsheet.py`
- Modify: `src/stock_research/performance_tearsheet.py`

- [ ] **Step 1: Write failing tear sheet trades test**

Test behavior: when result has `trades`, the writer emits `trades_path`; older results without trades still work.

- [ ] **Step 2: Run test to verify failure**

Run: `.venv/bin/pytest tests/test_performance_tearsheet.py -q`

Expected: FAIL until writer supports trades.

- [ ] **Step 3: Implement writer compatibility**

Use `getattr(result, "trades", pd.DataFrame())`.

- [ ] **Step 4: Run focused tests**

Run: `.venv/bin/pytest tests/test_performance_tearsheet.py tests/test_vectorized_topn_backtest.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/performance_tearsheet.py tests/test_performance_tearsheet.py
git commit -m "Write vectorized trade details in tear sheets"
```

## Task 3: Documentation And Verification

**Files:**
- Modify: `docs/astock-research-platform-v1.md`

- [ ] **Step 1: Update platform doc**

Add that vectorized TopN now outputs rebalance trade details.

- [ ] **Step 2: Run focused tests**

Run: `.venv/bin/pytest tests/test_vectorized_topn_backtest.py tests/test_performance_tearsheet.py -q`

Expected: PASS.

- [ ] **Step 3: Run full tests**

Run: `.venv/bin/pytest -q`

Expected: PASS.

- [ ] **Step 4: Commit docs and push**

Run:

```bash
git add docs/astock-research-platform-v1.md
git commit -m "Document vectorized trade details"
git push
```

## Self-Review

- Spec coverage: implements the Track 3 trade detail output gap without changing account-level portfolio backtests.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: trade row columns are `rebalance_date`, `asset_id`, `side`, `previous_weight`, `target_weight`, `delta_weight`, `turnover_contribution`, and `transaction_cost`.
