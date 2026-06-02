# Full-History Data Completion Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the remaining full-history A-share research datasets in a safe, observable, resumable order.

**Architecture:** Execute one wave at a time, with a read-only audit before and after every mutation wave. Earlier waves build dimensions, raw traceability, tradability, and benchmarks; later waves rebuild labels, features, factors, approvals, scores, and research outputs. Long jobs use existing idempotent CLI commands and are stopped immediately when audit output shows unexpected empty tables, stalled jobs, or source errors.

**Tech Stack:** Python, PostgreSQL, psycopg, pandas, pytest, `stock-research` CLI, PostgreSQL service `stock_research`, schemas `market`, `core`, `finance`, `factor`, `ingest`, `raw_baostock`, and `raw_akshare`.

---

## Baseline From 2026-05-12 Read-Only Audit

Use this baseline to verify that each wave moves only the intended datasets.

- `market_daily_bar`: `16,285,474` rows, `1990-12-19` through `2026-05-11`.
- `raw_baostock.daily_bar_payload`: `2` rows, only `2024-05-27`.
- `market.trading_calendar`: `10` rows, `2024-05-27` through `2024-05-31`.
- `market.adjustment_factor`: `5,036` rows, only `2024-05-27`.
- `market.corporate_action`: `0` rows.
- `market.index_daily_bar`: `2,832` rows, `2024-05-27` through `2026-05-08`.
- `market.index_constituent`: `300` rows, only `2024-05-31`, only one index.
- `core.industry_membership`: `808,161` rows, `1990-01-01` through `2026-05-08`.
- `market.industry_daily_bar`: `60,089` rows, `2023-06-01` through `2026-05-11`.
- `label_snapshot`: `20,585,204` rows, `1990-12-19` through `2026-04-28`; 5-day labels only start at `2023-06-01`.
- `feature_snapshot`: `56,123,299` rows, `1991-06-10` through `2026-05-08`.
- `factor.factor_daily`: `75,091,595` rows, `925` factor dates from `1991-06-24` through `2026-05-11`.
- `factor.factor_approval`: `2` approved factors, both under `flow_smoke_100d_v1`; `manual_v1` has `0` approved factors.
- `factor.stock_score_daily`: `manual_v1` has `10,403` rows for only `2026-05-08` and `2026-05-11`.
- `finance.balance_sheet`: `306,268` rows, `1989-12-31` through `2026-03-31`; `62` income-statement periods lack a matching balance sheet.
- `finance.cash_flow`: `305,401` rows, `1996-12-31` through `2026-03-31`; `39` income-statement periods lack a matching cash flow.
- Finance date quality: `93` rows have `announcement_date < report_period`.
- `ingest.batch_job`: `8,135` success, `7,881` skipped, no pending/running/failed jobs.

## Global Operating Rules

- Run one wave at a time. Do not start the next wave until the current wave's acceptance commands pass.
- Use `tmux` or another persistent terminal for any command expected to run longer than 30 minutes.
- Keep a shell log for every mutation wave:

```bash
cd /Users/xiwei/stock_research
mkdir -p logs/full_history_completion
export RUN_LOG="logs/full_history_completion/2026-05-12-wave.log"
```

- Before starting any mutation wave, verify that no ingest or backfill worker is already active:

```bash
ps -ef | rg "stock-research (run-ingest|run-daily-incremental|backfill-|load-bars|sync-index|build-|evaluate-factor|score-factor)" || true
/Users/xiwei/stock_research/.venv/bin/stock-research daily-health --trade-date 2026-05-12 --ingest-datasets baostock-finance,akshare-finance-statements --stale-minutes 60
```

- Stop the wave if a command exits non-zero, if `daily-health` reports `alert`, or if `data-audit` changes a previously non-empty table to `empty`.
- Record a backup/restore safety plan before destructive schema changes. This plan has no destructive schema changes, but the command should be available:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research migration-safety-check --backup-path /Users/xiwei/backups/stock_research_20260512.dump --source-service stock_research --restore-service stock_research_restore_check --dry-run
```

## Wave 0: Read-Only Baseline And Schema

**Purpose:** Confirm the database is reachable and schema/indexes are current before mutation.

**Files touched:** None.

- [ ] **Step 1: Apply current idempotent schema**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research apply-research-schema
```

Expected output contains:

```text
research_schema_applied
```

- [ ] **Step 2: Capture baseline audits**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research data-audit --expected-start-date 1990-12-01 | tee logs/full_history_completion/wave0-data-audit.txt
/Users/xiwei/stock_research/.venv/bin/stock-research finance-audit | tee logs/full_history_completion/wave0-finance-audit.txt
/Users/xiwei/stock_research/.venv/bin/stock-research ingest-status | tee logs/full_history_completion/wave0-ingest-status.txt
```

Expected output:

- `data_audit|market_daily_bar|ok|...`
- `finance_audit|missing_balance_sheet|blocked|rows|62`
- `finance_audit|missing_cash_flow|blocked|rows|39`
- `ingest_status|...` lines contain no `running`, `pending`, or `failed` status for production datasets.

- [ ] **Step 3: Commit no code**

No commit is required for Wave 0 because it only records local logs ignored by Git.

## Wave 1: Calendar And Raw Daily-Bar Traceability

**Purpose:** Fill the largest traceability gap: normalized bars exist back to 1990, but raw Baostock daily payload archive and trading calendar are short.

**Files touched:** Database tables `market.trading_calendar`, `raw_baostock.daily_bar_payload`, `market_daily_bar`.

- [ ] **Step 1: Seed trading calendar from existing market bars**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research seed-trading-calendar --start-date 1990-12-19 --end-date 2026-05-11 --exchanges SH,SZ --source-version derived_market_daily_bar_v1 | tee logs/full_history_completion/wave1-calendar.txt
```

Expected output begins with:

```text
trading_calendar_seeded|rows|
```

- [ ] **Step 2: Archive raw daily bars while reusing normalized load path**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research load-bars --start-date 1990-12-19 --end-date 2026-05-11 --archive-raw | tee logs/full_history_completion/wave1-load-bars-archive-raw.txt
```

Expected output includes counts for raw/qfq/hfq loads. Stop if the upstream source blocks or returns repeated empty tables for dates that already exist in `market_daily_bar`.

- [ ] **Step 3: Verify Wave 1**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research data-audit --expected-start-date 1990-12-01 | tee logs/full_history_completion/wave1-data-audit.txt
psql "service=stock_research" -At -F '|' -c "SELECT 'raw_baostock.daily_bar_payload', count(*), min(trade_date), max(trade_date), count(DISTINCT trade_date), count(DISTINCT asset_id) FROM raw_baostock.daily_bar_payload UNION ALL SELECT 'market.trading_calendar', count(*), min(trade_date), max(trade_date), count(DISTINCT trade_date), count(DISTINCT exchange) FROM market.trading_calendar;"
```

Expected output:

- `raw_baostock.daily_bar_payload` has substantially more than `2` rows.
- `market.trading_calendar` has substantially more than `10` rows and starts no later than `1990-12-19`.

- [ ] **Step 4: Commit Wave 1 logs only if logs are intentionally tracked**

No Git commit is required because this wave changes database state, not source files.

## Wave 2: Tradability, Adjustment Factors, And Corporate Actions

**Purpose:** Build point-in-time tradability and derived action datasets from completed market bars.

**Files touched:** Database tables `core.asset_status_daily`, `market.adjustment_factor`, `market.corporate_action`.

- [ ] **Step 1: Build asset status**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research build-asset-status --start-date 1990-12-19 --end-date 2026-05-11 --adjust-type hfq | tee logs/full_history_completion/wave2-asset-status.txt
```

Expected output:

```text
core_asset_status_daily_built
```

- [ ] **Step 2: Build adjustment factors**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research build-adjustment-factors --start-date 1990-12-19 --end-date 2026-05-11 --source-version derived_market_daily_bar_v1 | tee logs/full_history_completion/wave2-adjustment-factors.txt
```

Expected output:

```text
adjustment_factors_built
```

- [ ] **Step 3: Build corporate actions from factor changes**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research build-corporate-actions --start-date 1990-12-19 --end-date 2026-05-11 --source-version derived_adjustment_factor_v1 | tee logs/full_history_completion/wave2-corporate-actions.txt
```

Expected output:

```text
corporate_actions_built
```

- [ ] **Step 4: Verify Wave 2**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research data-audit --expected-start-date 1990-12-01 | tee logs/full_history_completion/wave2-data-audit.txt
psql "service=stock_research" -At -F '|' -c "SELECT 'market.adjustment_factor', count(*), min(trade_date), max(trade_date), count(DISTINCT trade_date), count(DISTINCT asset_id) FROM market.adjustment_factor UNION ALL SELECT 'market.corporate_action', count(*), min(event_date), max(event_date), count(DISTINCT event_date), count(DISTINCT asset_id) FROM market.corporate_action UNION ALL SELECT 'core.asset_status_daily', count(*), min(trade_date), max(trade_date), count(DISTINCT trade_date), count(DISTINCT asset_id) FROM core.asset_status_daily;"
```

Expected output:

- `market.adjustment_factor` has more than `5,036` rows and more than `1` distinct trade date.
- `market.corporate_action` is no longer empty unless the factor-change query legitimately finds no changes; if it stays empty, inspect `logs/full_history_completion/wave2-corporate-actions.txt` before continuing.
- `core.asset_status_daily` covers `1990-12-19` through `2026-05-11`.

## Wave 3: Index Data And Sector Bars

**Purpose:** Fill benchmark and sector dependencies needed by relative strength, sector factors, reports, and index-universe research.

**Files touched:** Database tables `market.index_daily_bar`, `market.index_constituent`, `market.industry_daily_bar`.

- [ ] **Step 1: Backfill supported index daily bars**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research sync-index-bars --start-date 1990-12-19 --end-date 2026-05-11 | tee logs/full_history_completion/wave3-index-bars.txt
```

Expected output begins with:

```text
index_daily_bars_synced|
```

- [ ] **Step 2: Backfill monthly constituent snapshots for supported targets**

This command uses the completed trading calendar to choose the last open trading day of each month.

```bash
cd /Users/xiwei/stock_research
psql "service=stock_research" -At -c "SELECT max(trade_date)::text FROM market.trading_calendar WHERE is_open AND trade_date BETWEEN '1990-12-19' AND '2026-05-11' GROUP BY date_trunc('month', trade_date) ORDER BY max(trade_date)" | while read trade_date; do
  /Users/xiwei/stock_research/.venv/bin/stock-research sync-index-constituents --trade-date "$trade_date" --index-ids SSE_50,CSI_300,CSI_500 --source-version baostock_monthly_snapshot_v1
done | tee logs/full_history_completion/wave3-index-constituents-monthly.txt
```

Expected output includes repeated lines like:

```text
index_constituents_synced|
```

Stop if Baostock rejects historical constituent dates repeatedly. If that happens, continue only after recording which index/date combinations are unavailable from the source.

- [ ] **Step 3: Rebuild industry daily bars across full market history**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research build-industry-bars --start-date 1990-12-19 --end-date 2026-05-11 --industry-system csrc --adjust-type hfq | tee logs/full_history_completion/wave3-industry-bars.txt
```

Expected output:

```text
market_industry_daily_bars_built
```

- [ ] **Step 4: Verify Wave 3**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research data-audit --expected-start-date 1990-12-01 | tee logs/full_history_completion/wave3-data-audit.txt
/Users/xiwei/stock_research/.venv/bin/stock-research research-preflight --start-date 1990-12-19 --end-date 2026-04-28 --horizons 5,10,20,60 --min-label-dates 252 --require-industry-membership | tee logs/full_history_completion/wave3-preflight.txt
```

Expected output:

- `market.index_daily_bar` starts earlier than `2024-05-27`.
- `market.index_constituent` has more than `1` distinct `start_date`.
- `market.industry_daily_bar` starts earlier than `2023-06-01`.
- `research_preflight|industry_membership|ok|...` appears, or the missing row count is inspected before continuing.

## Wave 4: Labels, Features, And Candidate Factors

**Purpose:** Make the model-ready layer match full market coverage.

**Files touched:** Database tables `label_snapshot`, `feature_snapshot`, `factor.factor_daily`.

- [ ] **Step 1: Backfill forward-return labels for all required horizons**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research backfill-labels --start-date 1990-12-19 --end-date 2026-04-28 --horizons 5,10,20,60 --adjust-type hfq | tee logs/full_history_completion/wave4-labels.txt
```

Expected output includes:

```text
labels_backfilled|
```

- [ ] **Step 2: Backfill P0 feature snapshots**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research backfill-features --start-date 1991-06-10 --end-date 2026-05-08 --lookback-bars 120 --adjust-type hfq --workers 4 --skip-complete | tee logs/full_history_completion/wave4-features.txt
```

Expected output includes:

```text
features_backfilled|
```

- [ ] **Step 3: Backfill all configured candidate factors**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research backfill-factor-daily --start-date 1991-06-24 --end-date 2026-05-11 --lookback-bars 130 --industry-system csrc --workers 4 --skip-complete --progress-interval 25 --exact-window | tee logs/full_history_completion/wave4-factor-daily.txt
```

Expected output includes:

```text
factor_daily_backfill|dates|
factor_daily_backfill|rows|
```

- [ ] **Step 4: Verify Wave 4**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research research-preflight --start-date 1991-06-24 --end-date 2026-04-28 --horizons 5,10,20,60 --min-label-dates 252 --require-industry-membership | tee logs/full_history_completion/wave4-preflight.txt
psql "service=stock_research" -At -F '|' -c "SELECT horizon, count(*), min(trade_date), max(trade_date), count(DISTINCT trade_date) FROM label_snapshot GROUP BY horizon ORDER BY horizon; SELECT calc_version, count(DISTINCT trade_date), min(trade_date), max(trade_date), count(*) FROM factor.factor_daily GROUP BY calc_version ORDER BY calc_version;"
```

Expected output:

- `research_preflight|coverage|ok|...`.
- `research_preflight|industry_membership|ok|...`.
- Horizon `5` starts earlier than `2023-06-01`.
- `factor.factor_daily` has substantially more than `925` distinct dates for `calc_version='v1'`.

## Wave 5: Factor Approval, Approved Scores, And Research Outputs

**Purpose:** Replace smoke score versions with validated `manual_v1` approved-only production scores.

**Files touched:** Database tables `factor.factor_eval_run`, `factor.factor_approval`, `factor.stock_score_daily`, backtest/report output directories under `reports/`.

- [ ] **Step 1: Evaluate default candidate factors with walk-forward validation**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research evaluate-factor-gate-batch --start-date 1991-06-24 --end-date 2026-04-28 --validation-start-date 2018-01-01 --horizons 5,10,20,60 --primary-horizon 5 --calc-version v1 --score-version manual_v1 --quantiles 5 --top-n 30 | tee logs/full_history_completion/wave5-factor-gate-batch.txt
```

Expected output includes one `factor_gate_batch|...` line per configured candidate factor.

- [ ] **Step 2: Verify approved factors exist for `manual_v1`**

```bash
cd /Users/xiwei/stock_research
psql "service=stock_research" -At -F '|' -c "SELECT score_version, status, count(*) FROM factor.factor_approval GROUP BY score_version, status ORDER BY score_version, status;"
```

Expected output includes at least one line:

```text
manual_v1|approved|
```

Stop if `manual_v1` has zero approved factors. Review `logs/full_history_completion/wave5-factor-gate-batch.txt` before scoring.

- [ ] **Step 3: Backfill approved-only production scores**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research backfill-approved-scores --start-date 1991-06-24 --end-date 2026-05-11 --score-version manual_v1 --calc-version v1 --adjust-type hfq | tee logs/full_history_completion/wave5-approved-scores.txt
```

Expected output includes:

```text
approved_score_backfill|dates|
approved_score_backfill|rows|
```

- [ ] **Step 4: Run approved-score research workflow**

```bash
cd /Users/xiwei/stock_research
.venv/bin/python -m stock_research.research_workflow_cli --start-date 1991-06-24 --end-date 2026-04-28 --score-version manual_v1 --top-n 20 --rebalance-frequency weekly --transaction-cost-bps 10 --max-positions 20 --strategy-id approved_topn_full_history_v1 | tee logs/full_history_completion/wave5-research-workflow.txt
```

Expected output includes:

```text
topn_research_workflow|
```

- [ ] **Step 5: Verify Wave 5**

```bash
cd /Users/xiwei/stock_research
psql "service=stock_research" -At -F '|' -c "SELECT score_version, count(*) AS rows, min(trade_date), max(trade_date), count(DISTINCT trade_date), count(DISTINCT asset_id) FROM factor.stock_score_daily WHERE score_version = 'manual_v1' GROUP BY score_version;"
```

Expected output shows `manual_v1` has more than `2` distinct trade dates and starts before `2026-05-08`.

## Wave 6: Finance Statement Gaps And Date Quality

**Purpose:** Close the remaining statement alignment gaps and identify unfixable source exceptions.

**Files touched:** Database tables `finance.balance_sheet`, `finance.cash_flow`, `raw_akshare.finance_payload`.

- [ ] **Step 1: Save exact missing statement periods**

```bash
cd /Users/xiwei/stock_research
psql "service=stock_research" -At -F '|' -c "SELECT i.asset_id, i.report_period, i.report_type FROM finance.income_statement i LEFT JOIN finance.balance_sheet b ON b.asset_id = i.asset_id AND b.report_period = i.report_period AND b.report_type = i.report_type WHERE b.asset_id IS NULL ORDER BY i.report_period, i.asset_id;" | tee logs/full_history_completion/wave6-missing-balance-sheet.txt
psql "service=stock_research" -At -F '|' -c "SELECT i.asset_id, i.report_period, i.report_type FROM finance.income_statement i LEFT JOIN finance.cash_flow c ON c.asset_id = i.asset_id AND c.report_period = i.report_period AND c.report_type = i.report_type WHERE c.asset_id IS NULL ORDER BY i.report_period, i.asset_id;" | tee logs/full_history_completion/wave6-missing-cash-flow.txt
psql "service=stock_research" -At -F '|' -c "SELECT 'balance_sheet', asset_id, report_period, report_type, announcement_date FROM finance.balance_sheet WHERE announcement_date < report_period UNION ALL SELECT 'cash_flow', asset_id, report_period, report_type, announcement_date FROM finance.cash_flow WHERE announcement_date < report_period ORDER BY 1, 3, 2;" | tee logs/full_history_completion/wave6-announcement-date-warnings.txt
```

Expected output files are non-empty for the current baseline.

- [ ] **Step 2: Re-run the AKShare statement batches that contain missing assets**

This Python snippet computes the original five-asset batch offsets for missing statement assets and re-runs only those offsets.

```bash
cd /Users/xiwei/stock_research
.venv/bin/python - <<'PY' | tee logs/full_history_completion/wave6-akshare-targeted-rerun.txt
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

Expected output includes `target_offsets|...` followed by `akshare_statement_rerun|...` lines. Stop if AKShare rate-limits repeatedly.

- [ ] **Step 3: Re-run finance audit**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research finance-audit | tee logs/full_history_completion/wave6-finance-audit-after-rerun.txt
```

Expected output:

- `missing_balance_sheet` row count is lower than `62`.
- `missing_cash_flow` row count is lower than `39`.
- If either count remains non-zero, preserve `wave6-missing-balance-sheet.txt` and `wave6-missing-cash-flow.txt` as source exceptions for manual review.

## Wave 7: Current-Day Incremental Catch-Up

**Purpose:** Bring the database from `2026-05-11` to the next completed trading date after bulk historical data is complete.

**Files touched:** Daily incremental tables touched by the DAG: market bars, asset status, index bars, index constituents, industry memberships, industry bars, labels, factors, approved scores, and reports.

- [ ] **Step 1: Dry-run the daily incremental DAG for 2026-05-12**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research run-daily-incremental --trade-date 2026-05-12 --score-version manual_v1 --top-n 30 --lookback-bars 130 --adjust-type hfq --source-service stock_hfq --industry-system csrc --dry-run | tee logs/full_history_completion/wave7-daily-incremental-dry-run.txt
```

Expected output lists planned steps from `sync_core_assets` through `run_daily_research_report`.

- [ ] **Step 2: Run the recorded daily incremental DAG**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research run-daily-incremental --trade-date 2026-05-12 --score-version manual_v1 --top-n 30 --lookback-bars 130 --adjust-type hfq --source-service stock_hfq --industry-system csrc --apply-daily-run-schema --record-run | tee logs/full_history_completion/wave7-daily-incremental-run.txt
```

Expected output:

```text
daily_incremental|status|success
```

If this fails after a step, resume with the next safe step. Example for a failure before scoring:

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research run-daily-incremental --trade-date 2026-05-12 --start-at build_factor_daily --record-run | tee logs/full_history_completion/wave7-daily-incremental-resume.txt
```

- [ ] **Step 3: Verify current-day health**

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research daily-health --trade-date 2026-05-12 --ingest-datasets baostock-finance,akshare-finance-statements --stale-minutes 60 | tee logs/full_history_completion/wave7-daily-health.txt
```

Expected output:

```text
daily_health|status|ok|alerts|0
```

## Final Acceptance

Run these commands after Wave 7:

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research data-audit --expected-start-date 1990-12-01 | tee logs/full_history_completion/final-data-audit.txt
/Users/xiwei/stock_research/.venv/bin/stock-research finance-audit | tee logs/full_history_completion/final-finance-audit.txt
/Users/xiwei/stock_research/.venv/bin/stock-research research-preflight --start-date 1991-06-24 --end-date 2026-04-28 --horizons 5,10,20,60 --min-label-dates 252 --require-industry-membership | tee logs/full_history_completion/final-preflight.txt
/Users/xiwei/stock_research/.venv/bin/stock-research export-research-snapshot --start-date 1991-06-24 --end-date 2026-04-28 --score-version manual_v1 --output-dir /Users/xiwei/stock_research/reports/snapshots/full_history_manual_v1_20260512 | tee logs/full_history_completion/final-snapshot-export.txt
```

Expected final state:

- `raw_baostock.daily_bar_payload` has historical coverage beyond one date.
- `market.trading_calendar` starts no later than `1990-12-19`.
- `market.adjustment_factor` has more than one distinct trade date.
- `market.corporate_action` is populated or explicitly documented as source-derived empty after factor-change inspection.
- `market.index_daily_bar` starts before `2024-05-27`.
- `market.index_constituent` has more than one distinct snapshot date.
- `market.industry_daily_bar` starts before `2023-06-01`.
- `label_snapshot` horizon `5` starts before `2023-06-01`.
- `factor.factor_daily` has more than `925` distinct `v1` dates.
- `factor.factor_approval` has at least one `manual_v1|approved` row.
- `factor.stock_score_daily` `manual_v1` has more than `2` distinct score dates.
- `research_preflight|coverage|ok|...` appears.
- `research_preflight|industry_membership|ok|...` appears.
- `daily_health|status|ok|alerts|0` appears for the most recent processed trading date.

## Recovery Commands

Use these when a long-running job is interrupted:

```bash
cd /Users/xiwei/stock_research
/Users/xiwei/stock_research/.venv/bin/stock-research ingest-status
/Users/xiwei/stock_research/.venv/bin/stock-research reset-stale-ingest-jobs --dataset akshare-finance-statements --older-than-minutes 60
/Users/xiwei/stock_research/.venv/bin/stock-research reset-stale-ingest-jobs --dataset baostock-finance --older-than-minutes 60
/Users/xiwei/stock_research/.venv/bin/stock-research daily-health --trade-date 2026-05-12 --ingest-datasets baostock-finance,akshare-finance-statements --stale-minutes 60
```

Use these after large mutation waves to refresh planner statistics:

```bash
psql "service=stock_research" -c "VACUUM ANALYZE market_daily_bar;"
psql "service=stock_research" -c "VACUUM ANALYZE raw_baostock.daily_bar_payload;"
psql "service=stock_research" -c "VACUUM ANALYZE market.trading_calendar;"
psql "service=stock_research" -c "VACUUM ANALYZE market.adjustment_factor;"
psql "service=stock_research" -c "VACUUM ANALYZE market.index_daily_bar;"
psql "service=stock_research" -c "VACUUM ANALYZE market.index_constituent;"
psql "service=stock_research" -c "VACUUM ANALYZE market.industry_daily_bar;"
psql "service=stock_research" -c "VACUUM ANALYZE label_snapshot;"
psql "service=stock_research" -c "VACUUM ANALYZE feature_snapshot;"
psql "service=stock_research" -c "VACUUM ANALYZE factor.factor_daily;"
psql "service=stock_research" -c "VACUUM ANALYZE factor.stock_score_daily;"
```

## Self-Review

- Spec coverage: the plan covers raw daily archive, trading calendar, adjustment factors, corporate actions, index bars, index constituents, industry bars, labels, features, factors, approvals, approved scores, finance gaps, current-day catch-up, audits, health checks, recovery, and final snapshot export.
- Placeholder scan: commands use concrete dates from the 2026-05-12 audit (`1990-12-19`, `1991-06-10`, `1991-06-24`, `2026-04-28`, `2026-05-08`, `2026-05-11`, `2026-05-12`) and concrete score/version names (`manual_v1`, `v1`, `csrc`, `hfq`).
- Type and command consistency: commands use existing `stock-research` parser options and existing PostgreSQL service name `stock_research`.
