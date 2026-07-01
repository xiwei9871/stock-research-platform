# Tech Bottleneck PIT Evidence Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a research-only no-lookahead replay that lets Tech Bottleneck report evidence affect rankings only after each report's publish/source date.

**Architecture:** Reuse existing Tech Bottleneck V1 ranking/backtest engine, but create a daily PIT evidence multiplier table from source-backed evidence rows where `source_date <= trade_date`. Compare official static baseline, static old-evidence adjustment, static all-new-evidence adjustment, and PIT all-new-evidence adjustment over the same local window.

**Tech Stack:** Python, pandas, existing `tech_bottleneck_v1`, `tech_bottleneck_candidates`, and `serenity_source_backed_evidence_fill` helpers.

---

### Task 1: Audit Evidence Grading Rules

**Files:**
- Read: `src/stock_research/serenity_source_backed_evidence_fill.py`
- Read: `outputs/research/tech_bottleneck_report_refresh_replay_20250101_20260629/combined_source_backed_evidence_seed.csv`

- [ ] **Step 1:** Confirm fields used for multiplier.

Expected fields:

```text
revenue_exposure_bucket
customer_certification_stage
supplier_concentration_type or supplier_concentration_evidence
```

### Task 2: Implement PIT Replay Script

**Files:**
- Create: `scripts/run_tech_bottleneck_pit_evidence_replay.py`

- [ ] **Step 1:** Build daily PIT multiplier by filtering evidence seed rows to `source_date <= trade_date`.
- [ ] **Step 2:** Apply multiplier to daily candidate snapshots and rerank per day.
- [ ] **Step 3:** Run Tech Bottleneck V1 backtest from rank snapshots.
- [ ] **Step 4:** Output metrics, selection-change diagnostics, and interpretation Markdown.

### Task 3: Run Research Replay

**Files:**
- Output: `outputs/research/tech_bottleneck_pit_evidence_replay_20250101_20260629/`

- [ ] **Step 1:** Run the script over requested window `2025-01-01` to latest local trade date.

### Task 4: Verify

**Checks:**

```text
baseline_vs_pit_evidence_replay.csv has 4 variants
pit_daily_evidence_multiplier.csv exists
pit_evidence_adjusted_daily_candidate_snapshots.csv exists
no evidence row with source_date > trade_date is used
final_interpretation.md answers whether PIT evidence improves PnL
```
