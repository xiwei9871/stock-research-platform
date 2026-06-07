# Intraday Factor Eval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI report that evaluates newly backfilled intraday stock and industry features against forward-return labels.

**Architecture:** Add a focused `intraday_factor_eval` module that loads factor-like frames from `factor.stock_intraday_features_daily`, joins optional industry features, reuses the existing multi-horizon factor evaluation functions, and writes Markdown/CSV artifacts. Add a CLI command that runs the report for a date range and configured horizons.

**Tech Stack:** Python, pandas, PostgreSQL via existing `db` helpers, argparse CLI, pytest.

---

### Task 1: Evaluation Module

**Files:**
- Create: `src/stock_research/intraday_factor_eval.py`
- Test: `tests/test_intraday_factor_eval.py`

- [ ] **Step 1: Write failing tests** for feature summaries, recommendation classification, and report writing using in-memory DataFrames.
- [ ] **Step 2: Run tests** with `./.venv/bin/pytest -q tests/test_intraday_factor_eval.py` and confirm failures are due to missing module/functions.
- [ ] **Step 3: Implement minimal module** with:
  - stock feature constants
  - report row summarization from `generate_multi_horizon_report`
  - Markdown and CSV writers
  - database loaders for stock intraday features and forward labels
- [ ] **Step 4: Run tests** until the new module tests pass.

### Task 2: CLI Command

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing CLI parser and dispatch tests** for `intraday-factor-eval`.
- [ ] **Step 2: Run targeted CLI tests** and confirm the command is missing.
- [ ] **Step 3: Add parser and dispatch** with `--start-date`, `--end-date`, `--horizons`, `--features`, `--freq`, `--adjust-type`, `--output-dir`, `--quantiles`, and `--top-n`.
- [ ] **Step 4: Run targeted tests** until parser and dispatch pass.

### Task 3: Real Data Verification

**Files:**
- Output only under `outputs/research/intraday_factor_eval/`

- [ ] **Step 1: Run focused tests** for factor eval, CLI, and intraday features.
- [ ] **Step 2: Run real report** for `2025-01-02` to `2026-06-05` with horizons `5,10,20,60`.
- [ ] **Step 3: Inspect generated CSV/Markdown** and report the strongest/weakest signals without promoting anything into the production score.
