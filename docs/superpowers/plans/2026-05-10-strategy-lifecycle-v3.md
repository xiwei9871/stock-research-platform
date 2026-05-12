# Strategy Lifecycle V3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an RQAlpha-style strategy lifecycle layer for V3 research without importing RQAlpha, connecting approved TopN score candidates to the vectorized TopN backtest engine.

**Architecture:** Implement a thin orchestration module that exposes lifecycle steps: `prepare_data`, `before_market`, `generate_signals`, `rebalance`, `after_market`, and `generate_report`. The lifecycle takes a config, loads score and price data through the existing vectorized adapter, creates candidate signals from current-date score rows only, runs the vectorized engine, and returns a structured research report. It does not change V3 thresholds, place orders, or touch broker integrations.

**Tech Stack:** Python, pandas, pytest, existing `stock_research.vectorized_topn_backtest`.

---

## File Structure

- Create `src/stock_research/strategy_lifecycle.py`: lifecycle dataclasses, step functions, and `run_topn_strategy_lifecycle`.
- Create `tests/test_strategy_lifecycle.py`: unit tests for orchestration order, signals, report shape, and dependency injection.
- Modify `docs/astock-research-platform-v1.md`: record lifecycle layer progress.

Do not modify `src/stock_research/cli.py` in this slice because it currently has unrelated uncommitted changes in the working tree.

## Task 1: Lifecycle Orchestration

**Files:**
- Create: `tests/test_strategy_lifecycle.py`
- Create: `src/stock_research/strategy_lifecycle.py`

- [ ] **Step 1: Write failing lifecycle orchestration test**

Test behavior: `run_topn_strategy_lifecycle` calls injected loader and backtest runner, returns a context with scores, prices, signals, backtest result, and a report whose lifecycle steps are ordered.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_strategy_lifecycle.py::test_run_topn_strategy_lifecycle_runs_ordered_steps_with_injected_dependencies -q`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement minimal lifecycle**

Add:
- `TopNStrategyConfig`
- `StrategyLifecycleContext`
- `prepare_data`
- `before_market`
- `generate_signals`
- `rebalance`
- `after_market`
- `generate_report`
- `run_topn_strategy_lifecycle`

- [ ] **Step 4: Run orchestration test**

Run: `.venv/bin/pytest tests/test_strategy_lifecycle.py::test_run_topn_strategy_lifecycle_runs_ordered_steps_with_injected_dependencies -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/strategy_lifecycle.py tests/test_strategy_lifecycle.py docs/superpowers/plans/2026-05-10-strategy-lifecycle-v3.md
git commit -m "Add TopN strategy lifecycle orchestration"
```

## Task 2: Signals And Report Semantics

**Files:**
- Modify: `tests/test_strategy_lifecycle.py`
- Modify: `src/stock_research/strategy_lifecycle.py`

- [ ] **Step 1: Write failing signal cap test**

Test behavior: `generate_signals` keeps only top-ranked candidates per date using `min(top_n, max_positions)` and never reads future dates.

- [ ] **Step 2: Write failing report test**

Test behavior: `generate_report` returns config, row counts, backtest summary, and latest equity.

- [ ] **Step 3: Run tests to verify failures**

Run: `.venv/bin/pytest tests/test_strategy_lifecycle.py -q`

Expected: FAIL until semantics are implemented.

- [ ] **Step 4: Implement signal and report semantics**

Keep implementation small and deterministic. Signals are a filtered score DataFrame, not executable orders.

- [ ] **Step 5: Run focused tests**

Run: `.venv/bin/pytest tests/test_strategy_lifecycle.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/stock_research/strategy_lifecycle.py tests/test_strategy_lifecycle.py
git commit -m "Add TopN lifecycle signal report semantics"
```

## Task 3: Documentation And Verification

**Files:**
- Modify: `docs/astock-research-platform-v1.md`

- [ ] **Step 1: Update platform doc**

Add a current-progress bullet under Stage 6 for the lifecycle layer.

- [ ] **Step 2: Run focused tests**

Run: `.venv/bin/pytest tests/test_strategy_lifecycle.py -q`

Expected: PASS.

- [ ] **Step 3: Run full tests**

Run: `.venv/bin/pytest -q`

Expected: PASS.

- [ ] **Step 4: Commit docs**

Run:

```bash
git add docs/astock-research-platform-v1.md
git commit -m "Document strategy lifecycle progress"
```

- [ ] **Step 5: Push**

Run: `git push`

Expected: branch pushes cleanly.

## Self-Review

- Spec coverage: covers RQAlpha-style lifecycle boundaries, data preparation, signal generation, rebalance/backtest call, after-market summary, and report output.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: public names are `TopNStrategyConfig`, `StrategyLifecycleContext`, `prepare_data`, `before_market`, `generate_signals`, `rebalance`, `after_market`, `generate_report`, and `run_topn_strategy_lifecycle`.
