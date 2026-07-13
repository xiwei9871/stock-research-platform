# LHB Phase 12A Multi-Context Decision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Phase 12A LHB decision artifact that combines raw LHB TopN selection, pre/event-day 5min context, and T+1 intraday confirmation into follow/watch/chase-control/retreat decisions.

**Architecture:** Keep Phase 11 confirmation untouched. Add a new builder in `src/stock_research/lhb_data.py` that accepts selected trades, minute bars, and existing T+1 confirmation detail, then writes decision/detail/summary/report outputs. Add one CLI command to run the builder from CSV artifacts.

**Tech Stack:** Python, pandas, pytest, existing `stock-research` CLI.

---

### Task 1: Decision Builder

**Files:**
- Modify: `tests/test_lhb_data.py`
- Modify: `src/stock_research/lhb_data.py`

- [ ] **Step 1: Write failing tests**

Add tests that prove:
- T-1/T context is classified as `preheated`, `event_day_failed`, or `event_day_strong`.
- T+1 `confirm_follow` plus non-failed context maps to `follow_pool`.
- T+1 `reject_follow` maps to `retreat_signal`.
- T+1 `confirm_but_chase_control` maps to `chase_control_pool`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/pytest tests/test_lhb_data.py -q -k "phase12a"
```

Expected: failure because `build_lhb_phase12a_multi_context_decision_v1` does not exist.

- [ ] **Step 3: Implement minimal builder**

Add:
- `LHB_PHASE12A_DECISION_COLUMNS`
- `LHB_PHASE12A_SUMMARY_COLUMNS`
- `build_lhb_phase12a_multi_context_decision_v1`
- helper functions for context window extraction, context classification, decision mapping, summary, and markdown.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
.venv/bin/pytest tests/test_lhb_data.py -q -k "phase12a"
```

Expected: phase12a tests pass.

### Task 2: CLI

**Files:**
- Modify: `tests/test_lhb_data.py`
- Modify: `src/stock_research/cli.py`

- [ ] **Step 1: Write failing CLI test**

Add a CLI test for:

```bash
stock-research lhb-phase12a-multi-context-decision-v1 \
  --selected-trades-path selected.csv \
  --minute-bars-path minute.csv \
  --intraday-detail-path intraday.csv \
  --output-dir out
```

- [ ] **Step 2: Run CLI test and verify RED**

Run:

```bash
.venv/bin/pytest tests/test_lhb_data.py -q -k "phase12a"
```

Expected: parser or import failure until CLI is implemented.

- [ ] **Step 3: Implement CLI**

Import the runner, add parser args, and print decision/summary/report paths.

- [ ] **Step 4: Run focused and full LHB tests**

Run:

```bash
.venv/bin/pytest tests/test_lhb_data.py -q
```

Expected: all LHB tests pass.

### Task 3: Real Artifact Run

**Files:**
- Use existing outputs under `outputs/research/lhb_full_market_20260101_20260608`

- [ ] **Step 1: Run Phase 12A command**

Run:

```bash
.venv/bin/stock-research lhb-phase12a-multi-context-decision-v1 \
  --selected-trades-path outputs/research/lhb_full_market_20260101_20260608/lhb_full_market_pool_selected_trades_20260101_20260608_v1.csv \
  --minute-bars-path outputs/research/lhb_full_market_20260101_20260608/lhb_full_market_topn_minute_bars_20260101_20260608.csv \
  --intraday-detail-path outputs/research/lhb_full_market_20260101_20260608/lhb_shortline_intraday_confirmation_detail_v1.csv \
  --output-dir outputs/research/lhb_full_market_20260101_20260608
```

- [ ] **Step 2: Inspect outputs**

Read decision and summary CSVs and report counts, returns, win rate, and drawdown by final decision.
