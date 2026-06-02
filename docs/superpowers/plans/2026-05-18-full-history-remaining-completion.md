# Full-History Remaining Completion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining full-history research gaps after Waves 1-4 by finishing technical-feature history, factor-gate approvals, approved-score promotion, finance-statement gap repair, and final current-day catch-up.

**Architecture:** Treat current Wave 1-4 database state as the baseline. Keep the two long-running backfills (`technical-features`, `factor-gate`) isolated and observable while executing only non-conflicting read-only or short mutation steps around them. Do not start Wave 5 approved-score backfill or Wave 7 final catch-up until `manual_v1` has at least one approved factor and technical-feature/factor-gate runs are in a healthy state.

**Tech Stack:** Python 3.14, PostgreSQL service `stock_research`, `stock-research` CLI, launchd watchdog jobs, pandas, psycopg.

---

## Scope

Included:

- Finish `factor.stock_technical_features_daily` backfill coverage.
- Finish `factor.factor_approval` for `manual_v1`.
- Backfill `manual_v1` approved scores and run approved-score research workflow.
- Repair remaining finance statement gaps and preserve source exceptions.
- Run final current-day catch-up and final audits.

Deferred:

- Pre-2006 index constituent remediation remains an explicit source-limitation item unless a new requirement promotes it back into scope.

## Current Baseline

- `technical-features` watchdog is running under `com.stockresearch.technical-feature-backfill-watchdog`.
- `factor-gate` watchdog is running under `com.stockresearch.factor-gate-backfill-watchdog`.
- `manual_v1` currently has zero approved factors.
- `manual_v1` scores currently cover only `103` trade dates.
- `finance-audit` still reports:
  - `missing_balance_sheet = 62`
  - `missing_cash_flow = 39`
  - `announcement_before_report_period = 93`
- `market_daily_bar` and `feature_snapshot` are ahead of `factor.factor_daily` / `label_snapshot`, so final catch-up is still pending.

## Task 1: Capture Fresh Remaining-Work Baseline

**Files:**
- Create/update: `logs/full_history_completion/waveR-baseline-20260518.txt`

- [ ] **Step 1: Capture current approvals, score coverage, and max dates**

Run:

```bash
cd /Users/xiwei/stock_research
{
  date '+baseline_started|%Y-%m-%d %H:%M:%S %z'
  psql service=stock_research -At -F '|' -c "SELECT score_version, status, count(*) FROM factor.factor_approval GROUP BY score_version, status ORDER BY score_version, status;"
  psql service=stock_research -At -F '|' -c "SELECT score_version, count(*), min(trade_date), max(trade_date), count(DISTINCT trade_date), count(DISTINCT asset_id) FROM factor.stock_score_daily GROUP BY score_version ORDER BY score_version;"
  psql service=stock_research -At -F '|' -c "SELECT 'market_daily_bar', max(trade_date) FROM market_daily_bar UNION ALL SELECT 'feature_snapshot', max(trade_date) FROM feature_snapshot UNION ALL SELECT 'factor_daily_v1', max(trade_date) FROM factor.factor_daily WHERE calc_version='v1' UNION ALL SELECT 'label_snapshot', max(trade_date) FROM label_snapshot;"
  .venv/bin/stock-research finance-audit
} | tee logs/full_history_completion/waveR-baseline-20260518.txt
```

Expected:

- `manual_v1|approved|` is absent or zero before factor-gate completes.
- `manual_v1` score coverage remains shorter than full history.
- `factor_daily_v1` / `label_snapshot` max dates lag `market_daily_bar`.

## Task 2: Finish `manual_v1` Factor Gate

**Files:**
- Observe/update: `logs/full_history_completion/wave5-factor-gate-watchdog.host.log`
- Observe/update: `logs/full_history_completion/wave5-factor-gate-batch-20260515.txt`

- [ ] **Step 1: Let optimized factor-gate watchdog continue until approvals appear**

Run:

```bash
cd /Users/xiwei/stock_research
psql service=stock_research -At -F '|' -c "SELECT score_version, status, count(*) FROM factor.factor_approval GROUP BY score_version, status ORDER BY score_version, status;"
tail -n 60 logs/full_history_completion/wave5-factor-gate-watchdog.host.log
```

Expected:

- At least one future check returns `manual_v1|approved|N` where `N > 0`.
- If watchdog exits non-zero or stalls without advancing, inspect the latest factor name and restart only after root-cause review.

- [ ] **Step 2: Stop here if no approved factor exists**

Gate:

- Do **not** run approved-score backfill until `manual_v1` has at least one approved factor.

## Task 3: Backfill Approved Scores And Run Research Workflow

**Files:**
- Create/update: `logs/full_history_completion/wave5-approved-scores-20260518.txt`
- Create/update: `logs/full_history_completion/wave5-research-workflow-20260518.txt`
- Create/update: `logs/full_history_completion/wave5-final-verification-20260518.txt`

- [ ] **Step 1: Backfill approved-only `manual_v1` scores after approvals exist**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/stock-research backfill-approved-scores \
  --start-date 1991-06-24 \
  --end-date 2026-05-15 \
  --score-version manual_v1 \
  --calc-version v1 \
  --adjust-type hfq \
  | tee logs/full_history_completion/wave5-approved-scores-20260518.txt
```

Expected:

- Output includes `approved_score_backfill|dates|`
- Output includes `approved_score_backfill|rows|` with non-zero rows.

- [ ] **Step 2: Run approved-score research workflow**

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
  | tee logs/full_history_completion/wave5-research-workflow-20260518.txt
```

Expected:

- Output includes `topn_research_workflow|`
- Exit code `0`

- [ ] **Step 3: Verify Wave 5 closure**

Run:

```bash
cd /Users/xiwei/stock_research
{
  psql service=stock_research -At -F '|' -c "SELECT score_version, status, count(*) FROM factor.factor_approval GROUP BY score_version, status ORDER BY score_version, status;"
  psql service=stock_research -At -F '|' -c "SELECT score_version, count(*), min(trade_date), max(trade_date), count(DISTINCT trade_date), count(DISTINCT asset_id) FROM factor.stock_score_daily WHERE score_version='manual_v1' GROUP BY score_version;"
} | tee logs/full_history_completion/wave5-final-verification-20260518.txt
```

Expected:

- `manual_v1|approved|N` exists with `N > 0`
- `manual_v1` score dates extend materially beyond `103` dates

## Task 4: Finish Technical-Feature History

**Files:**
- Observe/update: `logs/technical_feature_backfill_watchdog.host.log`

- [ ] **Step 1: Let the optimized technical-feature watchdog continue**

Run:

```bash
cd /Users/xiwei/stock_research
psql service=stock_research -At -F '|' -c "WITH rows AS (SELECT trade_date, count(*) AS n FROM factor.stock_technical_features_daily WHERE adjust_type='qfq' AND source='technical_features' AND source_data_version='market_daily_bar:qfq' AND calc_version='v1' GROUP BY trade_date) SELECT min(trade_date), max(trade_date), count(*) AS completed_dates, sum(n) AS total_rows FROM rows;"
tail -n 60 logs/technical_feature_backfill_watchdog.host.log
```

Expected:

- Frontier continues to advance.
- Do not overlap with ad-hoc technical-feature backfills unless watchdog stalls.

## Task 5: Repair Finance Statement Gaps

**Files:**
- Create/update: `logs/full_history_completion/wave6-missing-balance-sheet-20260518.txt`
- Create/update: `logs/full_history_completion/wave6-missing-cash-flow-20260518.txt`
- Create/update: `logs/full_history_completion/wave6-announcement-date-warnings-20260518.txt`
- Create/update: `logs/full_history_completion/wave6-akshare-targeted-rerun-20260518.txt`
- Create/update: `logs/full_history_completion/wave6-finance-audit-after-rerun-20260518.txt`

- [ ] **Step 1: Export exact finance gaps**

Run:

```bash
cd /Users/xiwei/stock_research
psql service=stock_research -At -F '|' -c "SELECT i.asset_id, i.report_period, i.report_type FROM finance.income_statement i LEFT JOIN finance.balance_sheet b ON b.asset_id = i.asset_id AND b.report_period = i.report_period AND b.report_type = i.report_type WHERE b.asset_id IS NULL ORDER BY i.report_period, i.asset_id;" | tee logs/full_history_completion/wave6-missing-balance-sheet-20260518.txt
psql service=stock_research -At -F '|' -c "SELECT i.asset_id, i.report_period, i.report_type FROM finance.income_statement i LEFT JOIN finance.cash_flow c ON c.asset_id = i.asset_id AND c.report_period = i.report_period AND c.report_type = i.report_type WHERE c.asset_id IS NULL ORDER BY i.report_period, i.asset_id;" | tee logs/full_history_completion/wave6-missing-cash-flow-20260518.txt
psql service=stock_research -At -F '|' -c "SELECT 'balance_sheet', asset_id, report_period, report_type, announcement_date FROM finance.balance_sheet WHERE announcement_date < report_period UNION ALL SELECT 'cash_flow', asset_id, report_period, report_type, announcement_date FROM finance.cash_flow WHERE announcement_date < report_period ORDER BY 1, 3, 2;" | tee logs/full_history_completion/wave6-announcement-date-warnings-20260518.txt
```

- [ ] **Step 2: Re-run only affected AKShare offsets**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python - <<'PY' | tee logs/full_history_completion/wave6-akshare-targeted-rerun-20260518.txt
from stock_research.db import connect, fetch_all
from stock_research.loaders.akshare_finance_statements import sync_finance_statements_for_assets

sql = """
WITH missing AS (
    SELECT i.asset_id
    FROM finance.income_statement i
    LEFT JOIN finance.balance_sheet b
      ON b.asset_id = i.asset_id
     AND b.report_period = i.report_period
     AND b.report_type = i.report_type
    WHERE b.asset_id IS NULL
    UNION
    SELECT i.asset_id
    FROM finance.income_statement i
    LEFT JOIN finance.cash_flow c
      ON c.asset_id = i.asset_id
     AND c.report_period = i.report_period
     AND c.report_type = i.report_type
    WHERE c.asset_id IS NULL
),
ordered AS (
    SELECT asset_id, row_number() over (ORDER BY asset_id) - 1 AS zero_based_index
    FROM core.asset_master
    WHERE akshare_code IS NOT NULL
      AND exchange IN ('SH', 'SZ')
)
SELECT DISTINCT (zero_based_index / 5)::int * 5 AS offset_value
FROM ordered
JOIN missing USING (asset_id)
ORDER BY offset_value
"""

with connect("stock_research") as conn:
    offsets = [int(row["offset_value"]) for row in fetch_all(conn, sql)]

print(f"target_offsets|{','.join(str(offset) for offset in offsets)}")
for offset in offsets:
    counts = sync_finance_statements_for_assets(limit=5, offset=offset)
    print(f"akshare_statement_rerun|offset|{offset}|{counts}")
PY
```

- [ ] **Step 3: Re-run finance audit**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/stock-research finance-audit | tee logs/full_history_completion/wave6-finance-audit-after-rerun-20260518.txt
```

Expected:

- Missing counts drop below baseline, or remaining rows are explicitly preserved as source exceptions.

## Task 6: Final Catch-Up And Final Acceptance

**Files:**
- Create/update: `logs/full_history_completion/wave7-daily-incremental-dry-run-20260518.txt`
- Create/update: `logs/full_history_completion/wave7-daily-incremental-run-20260518.txt`
- Create/update: `logs/full_history_completion/wave7-daily-health-20260518.txt`
- Create/update: `logs/full_history_completion/final-data-audit-20260518.txt`
- Create/update: `logs/full_history_completion/final-finance-audit-20260518.txt`
- Create/update: `logs/full_history_completion/final-preflight-20260518.txt`

- [ ] **Step 1: Wait for Wave 5 prerequisites**

Gate:

- Do not run final daily incremental catch-up until:
  - `manual_v1` has approved factors
  - `manual_v1` approved-score backfill has completed
  - major long-running historical backfills are stable

- [ ] **Step 2: Run final incremental catch-up**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/stock-research run-daily-incremental --trade-date 2026-05-15 --score-version manual_v1 --top-n 30 --lookback-bars 130 --adjust-type hfq --source-service stock_hfq --industry-system csrc --dry-run | tee logs/full_history_completion/wave7-daily-incremental-dry-run-20260518.txt
.venv/bin/stock-research run-daily-incremental --trade-date 2026-05-15 --score-version manual_v1 --top-n 30 --lookback-bars 130 --adjust-type hfq --source-service stock_hfq --industry-system csrc --apply-daily-run-schema --record-run | tee logs/full_history_completion/wave7-daily-incremental-run-20260518.txt
.venv/bin/stock-research daily-health --trade-date 2026-05-15 --ingest-datasets baostock-finance,akshare-finance-statements --stale-minutes 60 | tee logs/full_history_completion/wave7-daily-health-20260518.txt
```

- [ ] **Step 3: Run final acceptance audit**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/stock-research data-audit --expected-start-date 1990-12-01 | tee logs/full_history_completion/final-data-audit-20260518.txt
.venv/bin/stock-research finance-audit | tee logs/full_history_completion/final-finance-audit-20260518.txt
.venv/bin/stock-research research-preflight --start-date 1991-06-24 --end-date 2026-04-28 --horizons 5,10,20,60 --min-label-dates 252 --require-industry-membership | tee logs/full_history_completion/final-preflight-20260518.txt
```

Expected:

- `research_preflight|coverage|ok|`
- `manual_v1` approved scores are historical, not smoke-slice only
- finance gaps are either reduced or explicitly documented

## Self-Review

- Scope coverage: includes the remaining Wave 5/6/7 work plus the two still-running long backfills.
- Placeholder scan: all steps use concrete current paths, score versions, dates, and log destinations.
- Dependency check: approved-score and final catch-up tasks remain explicitly gated on factor-gate completion.
