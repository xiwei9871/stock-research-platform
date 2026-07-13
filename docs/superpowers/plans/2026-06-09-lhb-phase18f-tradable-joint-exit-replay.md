# LHB Phase18F Tradable Joint Exit Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert Phase18E joint weak signals into a T+1-compliant 5min tradable priority-exit replay.

**Architecture:** Use Phase18E state detail for opening-auction weakness and Phase18D daily close-auction lifecycle detail for the first daily weak close trigger. Reprice only exits that can be executed strictly after the entry day and after the close-auction trigger day, then compare against original Phase18C filled account trades.

**Tech Stack:** Python, pandas, existing PostgreSQL minute bar table, existing CLI and pytest.

---

### Task 1: Pure Replay Engine

- [ ] Add a failing test in `tests/test_lhb_data.py` for a trade with weak open plus negative close auction on entry day.
- [ ] Verify the adjusted exit is the next trading day's first 5min bar, not the entry day.
- [ ] Implement `build_lhb_phase18f_tradable_joint_exit_replay_v1`.
- [ ] Add a `next_30m_vwap` profile that prices from the first six 5min bars.

### Task 2: Summary and Report

- [ ] Add summary rows for baseline, `priority_exit_next_open_5min`, and `priority_exit_next_30m_vwap`.
- [ ] Report adjusted trade count, win rate, average return, median return, worst return, average return delta, and sell-flying proxy.
- [ ] Write CSV outputs and markdown report.

### Task 3: CLI and Data Loading

- [ ] Add optional `--minute-bars-path`; if absent, load `market.stock_minute_bar`.
- [ ] Add CLI command `lhb-phase18f-tradable-joint-exit-replay-v1`.
- [ ] Run Top3/Top5/Top10 enhanced over 2025-01-01 to 2026-06-05.
