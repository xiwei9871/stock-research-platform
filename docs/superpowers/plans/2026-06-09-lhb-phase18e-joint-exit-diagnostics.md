# LHB Phase18E Joint Exit Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable LHB joint-factor exit diagnostics report that prioritizes win-rate improvement first and sell-flying reduction second.

**Architecture:** Add a diagnostics layer in `stock_research.auction_data` that reads existing Phase18C account trades, Phase18D close-auction lifecycle summaries, Phase18 auction observation rows, and optional Phase16D intraday indicators. It classifies each filled trade into joint states, scans weak-signal filters, and reports win-rate impact plus sell-flying risk without changing the cash-account backtest engine.

**Tech Stack:** Python, pandas, existing CLI parser, pytest.

---

### Task 1: Joint State Classification

**Files:**
- Modify: `src/stock_research/auction_data.py`
- Test: `tests/test_auction_data.py`

- [ ] Write a failing test for `build_lhb_phase18e_joint_exit_state_detail_v1` using small DataFrames for account trades, auction observation, close lifecycle, and intraday indicators.
- [ ] Verify the test fails because the function is missing.
- [ ] Implement joins on `trade_date`, `ts_code`, `top_n`, `strategy` where available.
- [ ] Classify `joint_exit_state` using weak evidence counts:
  - `hard_exit`: at least three weak factors.
  - `soft_exit`: two weak factors.
  - `watch_hold`: one weak factor.
  - `strong_hold`: zero weak factors and at least one strong factor.
- [ ] Run the targeted test and keep it passing.

### Task 2: Rule Scan and Sell-Flying Summary

**Files:**
- Modify: `src/stock_research/auction_data.py`
- Test: `tests/test_auction_data.py`

- [ ] Write a failing test for `build_lhb_phase18e_joint_exit_rule_scan_v1`.
- [ ] Verify it fails because the function is missing.
- [ ] Implement rule profiles that remove or flag `hard_exit`, `soft_or_hard_exit`, and `mixed_close_plus_weak_open`.
- [ ] Report trade count, remaining count, excluded count, win rate, average return, median return, worst return, and average missed return when `exit_3d_return` is available.
- [ ] Run targeted tests.

### Task 3: CLI Report

**Files:**
- Modify: `src/stock_research/auction_data.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_schema.py`

- [ ] Add `build_lhb_phase18e_joint_exit_diagnostics_report_v1`.
- [ ] Add CLI command `lhb-phase18e-joint-exit-diagnostics-v1`.
- [ ] Write CSV outputs for state detail, rule scan, and markdown report.
- [ ] Add parser test for required paths and optional indicator path.
- [ ] Run `pytest tests/test_auction_data.py tests/test_schema.py::test_cli_accepts_baostock_ingestion_commands -q`.

### Task 4: Real Run

**Files:**
- Output directory: `outputs/research/lhb_phase18e_joint_exit_diagnostics_phase18c_20250101_20260605`

- [ ] Run Phase18E over Phase18C account trades and Phase18D close-auction lifecycle summaries.
- [ ] Include Phase18 auction observation detail for open-auction factors.
- [ ] Include Phase16D indicator detail as optional intraday evidence.
- [ ] Read the markdown and CSV summaries.
- [ ] Summarize whether filters improve win rate and what sell-flying risk remains.
