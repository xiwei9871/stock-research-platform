# Full-History Wave5 Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the accepted Wave 1-5 completion work by producing validated `manual_v1` approved factors, full-history approved scores, and approved-score research outputs while deferring pre-2006 index-constituent remediation.

**Architecture:** Treat Wave 1-4 as current upstream state and run Wave 5 as an idempotent promotion stage. First re-run factor gate evaluation against the completed full-history `factor.factor_daily` and `label_snapshot` tables, then backfill approved-only scores and run the approved-score research workflow. Keep every mutation logged under `logs/full_history_completion/` and verify database state after each step.

**Tech Stack:** Python 3.14, PostgreSQL service `stock_research`, `stock-research` CLI, pandas, psycopg, existing factor gate, approved scoring, and research workflow modules.

---

## Scope

Included:

- Re-evaluate `manual_v1` candidate factors over full-history data.
- Require at least one `manual_v1|approved` factor before score backfill.
- Backfill `factor.stock_score_daily` for approved `manual_v1` factors over the full available historical range.
- Run approved-score research workflow and capture outputs.
- Verify Wave 1-5 acceptance criteria with current database queries.

Deferred:

- Index constituent coverage before `2006-01-25`; record as source limitation for now.
- Wave 6 finance statement gap repair.

## Current Evidence

- `factor.factor_daily` `v1` currently spans `1991-06-24` through `2026-05-11`.
- Fresh preflight reached `research_preflight|coverage|ok|factor_dates|6583|complete_factor_dates|6575`.
- `manual_v1` currently has only rejected approvals:

```text
manual_v1|rejected|3
```

- `manual_v1` scores currently cover only `103` trade dates:

```text
manual_v1|520465|2024-05-27|2026-05-11|103|5203
```

## Task 1: Capture Fresh Pre-Wave5 Baseline

**Files:**

- Create/update: `logs/full_history_completion/wave5-pre-baseline-20260515.txt`

- [ ] **Step 1: Capture current approvals and score coverage**

Run:

```bash
cd /Users/xiwei/stock_research
{
  date '+baseline_started|%Y-%m-%d %H:%M:%S %z'
  psql service=stock_research -At -F '|' -c "SELECT score_version, status, count(*) FROM factor.factor_approval GROUP BY score_version, status ORDER BY score_version, status;"
  psql service=stock_research -At -F '|' -c "SELECT score_version, count(*), min(trade_date), max(trade_date), count(DISTINCT trade_date), count(DISTINCT asset_id) FROM factor.stock_score_daily GROUP BY score_version ORDER BY score_version;"
  psql service=stock_research -At -F '|' -c "SELECT min(trade_date), max(trade_date), count(*) FROM factor.factor_daily WHERE calc_version='v1' AND trade_date='2026-05-11';"
} | tee logs/full_history_completion/wave5-pre-baseline-20260515.txt
```

Expected:

- `manual_v1|rejected|3` appears before re-evaluation.
- Existing `manual_v1` score coverage is short and starts at `2024-05-27`.
- `factor.factor_daily` has rows on `2026-05-11`.

## Task 2: Re-Evaluate Candidate Factors For `manual_v1`

**Files:**

- Create/update: `logs/full_history_completion/wave5-factor-gate-batch-20260515.txt`

- [ ] **Step 1: Run full-history walk-forward factor gate**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/stock-research evaluate-factor-gate-batch \
  --start-date 1991-06-24 \
  --end-date 2026-04-28 \
  --validation-start-date 2018-01-01 \
  --horizons 5,10,20,60 \
  --primary-horizon 5 \
  --calc-version v1 \
  --score-version manual_v1 \
  --quantiles 5 \
  --top-n 30 \
  | tee logs/full_history_completion/wave5-factor-gate-batch-20260515.txt
```

Expected:

- One `factor_gate_batch|...` line per configured candidate factor.
- At least one line contains `|approved|passed_thresholds|`.

- [ ] **Step 2: Verify `manual_v1` approvals**

Run:

```bash
cd /Users/xiwei/stock_research
psql service=stock_research -At -F '|' -c "SELECT score_version, status, count(*) FROM factor.factor_approval GROUP BY score_version, status ORDER BY score_version, status;"
```

Expected:

- At least one `manual_v1|approved|N` line where `N > 0`.
- If no factor is approved, stop and inspect `logs/full_history_completion/wave5-factor-gate-batch-20260515.txt`; do not backfill scores.

## Task 3: Backfill Approved-Only `manual_v1` Scores

**Files:**

- Create/update: `logs/full_history_completion/wave5-approved-scores-20260515.txt`

- [ ] **Step 1: Backfill scores for approved factors only**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/stock-research backfill-approved-scores \
  --start-date 1991-06-24 \
  --end-date 2026-05-11 \
  --score-version manual_v1 \
  --calc-version v1 \
  --adjust-type hfq \
  | tee logs/full_history_completion/wave5-approved-scores-20260515.txt
```

Expected:

- Output includes `approved_score_backfill|dates|`.
- Output includes `approved_score_backfill|rows|` with a non-zero row count.

- [ ] **Step 2: Verify score coverage**

Run:

```bash
cd /Users/xiwei/stock_research
psql service=stock_research -At -F '|' -c "SELECT score_version, count(*) AS rows, min(trade_date), max(trade_date), count(DISTINCT trade_date), count(DISTINCT asset_id) FROM factor.stock_score_daily WHERE score_version = 'manual_v1' GROUP BY score_version;"
```

Expected:

- `manual_v1` starts before `2024-05-27`.
- `manual_v1` has substantially more than `103` distinct trade dates.

## Task 4: Run Approved-Score Research Workflow

**Files:**

- Create/update: `logs/full_history_completion/wave5-research-workflow-20260515.txt`
- Create/update: research workflow outputs under `reports/` or the workflow's configured output path.

- [ ] **Step 1: Run full-history TopN research workflow**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python -m stock_research.research_workflow_cli \
  --start-date 1991-06-24 \
  --end-date 2026-04-28 \
  --score-version manual_v1 \
  --top-n 20 \
  --rebalance-frequency weekly \
  --transaction-cost-bps 10 \
  --max-positions 20 \
  --strategy-id approved_topn_full_history_v1 \
  | tee logs/full_history_completion/wave5-research-workflow-20260515.txt
```

Expected:

- Output includes `topn_research_workflow|`.
- Workflow completes with exit code `0`.

## Task 5: Final Verification For Accepted 1-5 Scope

**Files:**

- Create/update: `logs/full_history_completion/wave5-final-verification-20260515.txt`

- [ ] **Step 1: Verify accepted scope**

Run:

```bash
cd /Users/xiwei/stock_research
{
  date '+verification_started|%Y-%m-%d %H:%M:%S %z'
  psql service=stock_research -At -F '|' -c "SELECT 'raw_daily', count(*), min(trade_date), max(trade_date), count(DISTINCT trade_date), count(DISTINCT asset_id) FROM raw_baostock.daily_bar_payload UNION ALL SELECT 'market_daily', count(*), min(trade_date), max(trade_date), count(DISTINCT trade_date), count(DISTINCT asset_id) FROM market_daily_bar;"
  psql service=stock_research -At -F '|' -c "SELECT 'factor_daily_v1', count(DISTINCT trade_date), min(trade_date), max(trade_date), count(*) FROM factor.factor_daily WHERE calc_version='v1';"
  psql service=stock_research -At -F '|' -c "SELECT score_version, status, count(*) FROM factor.factor_approval GROUP BY score_version, status ORDER BY score_version, status;"
  psql service=stock_research -At -F '|' -c "SELECT score_version, count(*), min(trade_date), max(trade_date), count(DISTINCT trade_date), count(DISTINCT asset_id) FROM factor.stock_score_daily WHERE score_version='manual_v1' GROUP BY score_version;"
  .venv/bin/stock-research finance-audit
} | tee logs/full_history_completion/wave5-final-verification-20260515.txt
```

Expected:

- Raw daily payload is current through the accepted archive range.
- `factor_daily_v1` remains full-history.
- `manual_v1` has approved factors.
- `manual_v1` score dates are full-history or the remaining gap is explicitly captured.
- Finance audit still reports Wave 6 gaps; this is acceptable because Wave 6 is deferred.

## Self-Review

- Spec coverage: Tasks cover accepted items 1-5 and explicitly defer item 6 plus Wave 6 finance repair.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: commands use existing CLI names and current concrete versions: `manual_v1`, `v1`, `hfq`, `csrc`.
